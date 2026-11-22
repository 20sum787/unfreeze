package org.medmech.unfreeze

import android.app.Activity
import android.app.AlertDialog
import android.net.Uri
import android.os.Bundle
import android.webkit.*
import androidx.webkit.*
import kotlinx.coroutines.*
import org.json.JSONObject

/**
 * Only local, packaged pages can call the native adapter. No arbitrary URL or JavaScript is
 * executed.
 */
class MainActivity : Activity() {
    private lateinit var web: WebView
    private lateinit var player: CuePlayer
    private lateinit var storage: PhoneStorage
    private var previewDialog: AlertDialog? = null
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    private var board: LanRepository? = null
    private var channel = 0
    private var visible = false
    private val pendingPlay = mutableMapOf<CueKey, Int>()
    private val routes =
        setOf(
            "GET /v1/capabilities",
            "GET /v1/settings",
            "GET /v1/state",
            "PUT /v1/settings",
            "POST /v1/session/start",
            "POST /v1/session/stop",
            "POST /v1/haptics/preview",
            "POST /v1/buzzer/preview",
            "POST /v1/buzzer/stop",
            "POST /v1/haptics/stop",
        )
    private val events =
        setOf(
            "client.status",
            "debug.subscribe",
            "debug.unsubscribe",
            "cue.audio.ready",
            "cue.audio.started",
            "cue.audio.failed",
        )

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        storage = PhoneStorage(this)
        WebView.setWebContentsDebuggingEnabled(
            (applicationInfo.flags and android.content.pm.ApplicationInfo.FLAG_DEBUGGABLE) != 0
        )
        web = WebView(this)
        player =
            CuePlayer(this) { event, key ->
                val id = pendingPlay.remove(key)
                if (id != null)
                    result(
                        id,
                        event == "started",
                        if (event == "started") true else "Playback interrupted",
                    )
                if (key != null && event != "started")
                    deliver(
                        json(
                            "signal" to "audio.end",
                            "body" to json("sessionId" to key.sessionId, "cueId" to key.cueId),
                        )
                    )
            }
        val loader =
            WebViewAssetLoader.Builder()
                .addPathHandler("/assets/", WebViewAssetLoader.AssetsPathHandler(this))
                .build()
        web.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            allowFileAccess = false
            allowContentAccess = false
        }
        web.webViewClient =
            object : WebViewClient() {
                override fun shouldOverrideUrlLoading(v: WebView, r: WebResourceRequest) = true

                override fun shouldInterceptRequest(
                    v: WebView,
                    r: WebResourceRequest,
                ): WebResourceResponse =
                    loader.shouldInterceptRequest(r.url)
                        ?: WebResourceResponse(
                            "text/plain",
                            "utf-8",
                            403,
                            "Forbidden",
                            emptyMap(),
                            null,
                        )
            }
        if (!WebViewFeature.isFeatureSupported(WebViewFeature.WEB_MESSAGE_LISTENER)) {
            setContentView(
                android.widget.TextView(this).apply {
                    setText(R.string.update_webview)
                }
            )
            return
        }
        WebViewCompat.addWebMessageListener(
            web,
            "UnfreezeNative",
            setOf("https://appassets.androidplatform.net"),
        ) { _, msg, _, main, _ ->
            if (main)
                scope.launch {
                    val m = runCatching { JSONObject(msg.data ?: "") }.getOrNull() ?: return@launch
                    val id = m.optInt("id", -1)
                    try {
                        val answer =
                            dispatch(m.getString("op"), m.optJSONObject("args") ?: JSONObject(), id)
                        if (answer != null) result(id, true, answer)
                    } catch (e: Exception) {
                        android.util.Log.w("Unfreeze", "Native request ${m.optString("op")} failed (${e.javaClass.simpleName})")
                        result(
                            id,
                            false,
                            when (e) {
                                is ApiError -> "HTTP " + e.status
                                is java.io.IOException -> "Board unreachable"
                                else -> e.localizedMessage?.take(160) ?: "Request failed"
                            },
                        )
                    }
                }
        }
        web.setOnApplyWindowInsetsListener { v, insets ->
            @Suppress("DEPRECATION")
            v.setPadding(
                insets.systemWindowInsetLeft,
                insets.systemWindowInsetTop,
                insets.systemWindowInsetRight,
                insets.systemWindowInsetBottom,
            )
            insets
        }
        setContentView(web)
        web.loadUrl("https://appassets.androidplatform.net/assets/index.html")
    }

    private fun deliver(message: JSONObject) {
        val value = JSONObject.quote(message.toString())
        web.evaluateJavascript(
            "window.unfreezeReceive && window.unfreezeReceive(" + value + ")",
            null,
        )
    }

    private fun result(id: Int, ok: Boolean, value: Any) =
        deliver(json("id" to id, "ok" to ok, "value" to value))

    private suspend fun dispatch(op: String, a: JSONObject, id: Int): Any? {
        return when (op) {
            "camera.preview" -> {
                showCameraPreview(board?.endpoint ?: LanRepository.normalize(a.getString("host")))
                true
            }
            "health" -> {
                LanRepository(a.getString("host")).health()
                true
            }
            "open" -> {
                val generation = ++channel
                board?.close()
                board = null
                val code = a.optString("code")
                val saved = if (code.isBlank()) storage.read() else null
                val repo = LanRepository(a.getString("host"), saved)
                repo.health()
                check(channel == generation)
                if (code.isNotBlank()) {
                    val p = repo.pair(code)
                    check(channel == generation)
                    storage.save(p)
                } else require(saved?.endpoint == repo.endpoint) { "Enter the pairing code" }
                board = repo
                generation
            }
            "listen" -> {
                val generation = a.getInt("channel")
                require(channel == generation)
                requireNotNull(board).listen { event ->
                    scope.launch {
                        if (channel == generation)
                            deliver(
                                json(
                                    "channel" to generation,
                                    "signal" to event.name,
                                    "body" to event.body,
                                )
                            )
                    }
                }
                true
            }
            "request" -> {
                require(channel == a.getInt("channel"))
                val method = a.getString("method")
                val path = a.getString("path")
                require(method + " " + path in routes)
                requireNotNull(board).request(method, path, a.optJSONObject("body"))
            }
            "send" -> {
                val name = a.getString("name")
                require(name in events && channel == a.getInt("channel"))
                board?.send(name, a.getJSONObject("body"))
                true
            }
            "close" -> {
                if (a.getInt("channel") == channel) {
                    channel++
                    board?.close()
                    board = null
                    player.silence()
                }
                true
            }
            "forget" -> {
                storage.forget()
                true
            }
            "audio.select" -> {
                player.select(a.getString("track"), a.getDouble("volume").toFloat())
                true
            }
            "audio.ready" -> player.ready && visible
            "audio.audition" -> {
                require(visible)
                player.audition()
                true
            }
            "audio.stop" -> {
                player.silence()
                true
            }
            "audio.play" -> {
                require(visible && player.ready)
                val key = CueKey(a.getString("sessionId"), a.getString("cueId"))
                pendingPlay[key] = id
                player.play(key)
                null
            }
            else -> throw IllegalArgumentException("Unsupported client operation")
        }
    }

    override fun onResume() {
        super.onResume()
        visible = true
        web.onResume()
        deliver(json("signal" to "foreground", "body" to true))
    }

    private fun showCameraPreview(endpoint: String) {
        if (previewDialog != null) return
        val origin = Uri.parse(endpoint)
        // A separate, read-only viewer keeps the controller and its audio session in the foreground.
        val viewer = WebView(this).apply {
            settings.javaScriptEnabled = true
            settings.allowFileAccess = false
            settings.allowContentAccess = false
            webViewClient = object : WebViewClient() {
                override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                    val url = request.url
                    return url.scheme != origin.scheme || url.host != origin.host || url.userInfo != null
                }
            }
        }
        val dialog = AlertDialog.Builder(this)
            .setView(viewer)
            .setPositiveButton(android.R.string.ok, null)
            .create()
        dialog.setOnDismissListener {
            (viewer.parent as? android.view.ViewGroup)?.removeView(viewer)
            viewer.stopLoading()
            viewer.destroy()
            previewDialog = null
        }
        previewDialog = dialog
        dialog.show()
        dialog.window?.setLayout(android.view.ViewGroup.LayoutParams.MATCH_PARENT,
                                 android.view.ViewGroup.LayoutParams.MATCH_PARENT)
        viewer.loadUrl("$endpoint/preview")
    }

    override fun onPause() {
        visible = false
        board?.send("client.status", json("audioReady" to false))
        player.silence()
        deliver(json("signal" to "foreground", "body" to false))
        web.onPause()
        super.onPause()
    }

    @Deprecated("Activity compatibility")
    override fun onBackPressed() {
        web.evaluateJavascript("window.unfreezeBack ? window.unfreezeBack() : false") {
            if (it != "true") super.onBackPressed()
        }
    }

    override fun onDestroy() {
        previewDialog?.dismiss()
        scope.cancel()
        channel++
        board?.close()
        player.close()
        web.destroy()
        super.onDestroy()
    }
}
