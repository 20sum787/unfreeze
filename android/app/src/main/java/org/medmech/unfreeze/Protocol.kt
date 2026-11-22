package org.medmech.unfreeze

import org.json.JSONObject

fun json(vararg values: Pair<String, Any?>) =
    JSONObject().apply { values.forEach { (k, v) -> put(k, v ?: JSONObject.NULL) } }

data class CueKey(val sessionId: String, val cueId: String)

data class Event(val name: String, val body: JSONObject)

data class Pairing(val endpoint: String, val deviceId: String, val token: String) {
    override fun toString() = "Pairing(deviceId=" + deviceId + ")"
}

class ApiError(val status: Int) : Exception("Board returned HTTP " + status)

interface DeviceRepository {
    suspend fun health()

    suspend fun pair(code: String): Pairing

    suspend fun request(method: String, path: String, body: JSONObject? = null): JSONObject

    fun listen(onEvent: (Event) -> Unit)

    fun send(name: String, body: JSONObject)

    fun close()
}
