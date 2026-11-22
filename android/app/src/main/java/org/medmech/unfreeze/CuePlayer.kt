package org.medmech.unfreeze

import android.content.Context
import android.net.Uri
import android.os.Handler
import android.os.Looper
import androidx.media3.common.*
import androidx.media3.exoplayer.ExoPlayer

/** One preloaded, finite local track. Every callback runs on the main looper. */
class CuePlayer(private val context: Context, val update: (String, CueKey?) -> Unit) :
    Player.Listener {
    private val engine = ExoPlayer.Builder(context).build()
    private val handler = Handler(Looper.getMainLooper())
    private val timeout = Runnable { finish("failed") }
    private val catalog = context.assets.list("tracks").orEmpty().toSet()
    private var track: String? = null
    private var key: CueKey? = null
    private var audition = false
    private var reported = false
    val ready
        get() = engine.volume > 0f && engine.playbackState == Player.STATE_READY && key == null

    init {
        engine.setAudioAttributes(
            AudioAttributes.Builder()
                .setUsage(C.USAGE_MEDIA)
                .setContentType(C.AUDIO_CONTENT_TYPE_MUSIC)
                .build(),
            true,
        )
        engine.addListener(this)
    }

    fun select(value: String, gain: Float) {
        require(value + ".wav" in catalog) { "Unknown audio track" }
        engine.volume = gain.coerceIn(0f, 1f)
        if (track == value) return
        finish("cancel")
        track = value
        engine.setMediaItem(MediaItem.fromUri(Uri.parse("asset:///tracks/" + value + ".wav")))
        engine.prepare()
    }

    fun audition() {
        if (key == null) {
            stopPreview()
            audition = true
            engine.seekTo(0)
            engine.play()
        }
    }

    fun stopPreview() {
        if (audition) finish("cancel")
    }

    fun play(cue: CueKey) {
        stopPreview()
        key = cue
        reported = false
        handler.postDelayed(timeout, 600)
        engine.seekTo(0)
        engine.play()
    }

    fun silence() {
        finish("cancel")
    }

    private fun finish(result: String) {
        val previous = key
        key = null
        audition = false
        reported = false
        handler.removeCallbacks(timeout)
        engine.pause()
        if (engine.mediaItemCount > 0) engine.seekTo(0)
        if (previous != null) update(result, previous)
    }

    override fun onIsPlayingChanged(isPlaying: Boolean) {
        if (isPlaying && key != null && !reported) {
            reported = true
            handler.removeCallbacks(timeout)
            handler.postDelayed(timeout, 12_000)
            update("started", key)
        }
    }

    override fun onPlaybackStateChanged(playbackState: Int) {
        if (playbackState == Player.STATE_ENDED) finish("finished")
    }

    override fun onPlayerError(error: PlaybackException) {
        finish("failed")
    }

    fun close() {
        handler.removeCallbacksAndMessages(null)
        engine.removeListener(this)
        engine.release()
    }
}
