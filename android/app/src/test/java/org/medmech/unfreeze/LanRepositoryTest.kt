package org.medmech.unfreeze

import kotlinx.coroutines.runBlocking
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.Assert.*
import org.junit.Test

class LanRepositoryTest {
    @Test
    fun pairingIsPublicAndControlIsOriginBound() = runBlocking {
        val server = MockWebServer()
        server.start()
        try {
            val endpoint = server.url("/").toString()
            val client = LanRepository(endpoint)
            server.enqueue(MockResponse().setBody("""{"ok":true,"apiVersion":1}"""))
            client.health()
            assertNull(server.takeRequest().getHeader("Authorization"))
            server.enqueue(MockResponse().setBody("""{"deviceId":"uno","token":"fixture-key"}"""))
            client.pair("123456")
            val pairing = server.takeRequest()
            assertEquals("/v1/pair", pairing.path)
            assertNull(pairing.getHeader("Authorization"))
            server.enqueue(MockResponse().setBody("{}"))
            client.request("GET", "/v1/state")
            assertEquals("Bearer fixture-key", server.takeRequest().getHeader("Authorization"))
            val other =
                LanRepository(endpoint, Pairing("http://elsewhere:7000", "uno", "fixture-key"))
            assertTrue(runCatching { other.request("GET", "/v1/state") }.isFailure)
        } finally {
            server.shutdown()
        }
    }

    @Test
    fun credentialsAreAbsentFromPrintedPairing() {
        assertFalse(
            Pairing("http://host", "uno", "secret-value").toString().contains("secret-value")
        )
    }
}
