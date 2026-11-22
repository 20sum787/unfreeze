package org.medmech.unfreeze

import io.socket.client.IO
import io.socket.client.Socket
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject

/**
 * Credentials are scoped to a single explicit origin. Redirects and command retries are disabled.
 */
class LanRepository(address: String, saved: Pairing? = null) : DeviceRepository {
    val endpoint = normalize(address)
    private val http =
        OkHttpClient.Builder()
            .followRedirects(false)
            .followSslRedirects(false)
            .retryOnConnectionFailure(false)
            .callTimeout(4, TimeUnit.SECONDS)
            .build()
    private var credential = saved?.takeIf { it.endpoint == endpoint }
    private var socket: Socket? = null

    override suspend fun request(method: String, path: String, body: JSONObject?) =
        withContext(Dispatchers.IO) {
            require(path.startsWith("/v1/") && '?' !in path)
            val req = Request.Builder().url(endpoint + path)
            val public = path in setOf("/v1/health", "/v1/pair")
            if (!public) req.header("Authorization", "Bearer " + requireNotNull(credential).token)
            val payload =
                if (method == "GET") null
                else
                    (body ?: JSONObject())
                        .toString()
                        .toRequestBody("application/json".toMediaType())
            http.newCall(req.method(method, payload).build()).execute().use { response ->
                if (!response.isSuccessful) throw ApiError(response.code)
                val content = response.body?.string().orEmpty()
                if (content.isBlank()) JSONObject() else JSONObject(content)
            }
        }

    override suspend fun health() {
        val result = request("GET", "/v1/health")
        require(result.getBoolean("ok") && result.getInt("apiVersion") == 1) {
            "Incompatible board API"
        }
    }

    override suspend fun pair(code: String): Pairing {
        val result = request("POST", "/v1/pair", json("code" to code))
        return Pairing(endpoint, result.getString("deviceId"), result.getString("token")).also {
            credential = it
        }
    }

    override fun listen(onEvent: (Event) -> Unit) {
        close()
        val key = requireNotNull(credential)
        val link =
            IO.socket(
                endpoint,
                IO.Options.builder().setForceNew(true).setReconnection(true).build(),
            )
        socket = link
        link.on(Socket.EVENT_CONNECT) {
            onEvent(Event("transport.connect", JSONObject()))
            link.emit(
                "client.hello",
                json("token" to key.token, "deviceId" to key.deviceId, "apiVersion" to 1),
            )
        }
        link.on(Socket.EVENT_DISCONNECT) { onEvent(Event("transport.disconnect", JSONObject())) }
        link.on(Socket.EVENT_CONNECT_ERROR) { onEvent(Event("transport.error", JSONObject())) }
        listOf(
                "status.snapshot",
                "cue.audio.offer",
                "cue.audio.play",
                "cue.audio.cancel",
                "debug.event",
                "debug.telemetry",
                "auth.error",
            )
            .forEach { name ->
                link.on(name) { args ->
                    (args.firstOrNull() as? JSONObject)?.let { onEvent(Event(name, it)) }
                }
            }
        link.connect()
    }

    override fun send(name: String, body: JSONObject) {
        socket?.takeIf { it.connected() }?.emit(name, body)
    }

    override fun close() {
        socket?.off()
        socket?.disconnect()
        socket = null
    }

    companion object {
        fun normalize(input: String): String {
            val s = input.trim()
            val url = (if ("://" in s) s else "http://" + s).toHttpUrl()
            require(
                url.username.isEmpty() &&
                    url.password.isEmpty() &&
                    url.encodedPath == "/" &&
                    url.query == null &&
                    url.fragment == null
            ) {
                "Enter the board host and port only"
            }
            return url.toString().trimEnd('/')
        }
    }
}
