package org.medmech.unfreeze

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec
import org.json.JSONObject

class PhoneStorage(private val context: Context) {
    private val secret = context.getSharedPreferences("pairing-v1", Context.MODE_PRIVATE)

    private fun key(): SecretKey {
        val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (store.getKey("unfreeze-pair", null) as? SecretKey)?.let {
            return it
        }
        val generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
        generator.init(
            KeyGenParameterSpec.Builder(
                    "unfreeze-pair",
                    KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT,
                )
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .build()
        )
        return generator.generateKey()
    }

    fun save(p: Pairing) {
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.ENCRYPT_MODE, key())
        val value = json("endpoint" to p.endpoint, "deviceId" to p.deviceId, "token" to p.token)
        fun encode(bytes: ByteArray) = Base64.encodeToString(bytes, Base64.NO_WRAP)
        secret
            .edit()
            .putString("iv", encode(cipher.iv))
            .putString("data", encode(cipher.doFinal(value.toString().toByteArray())))
            .apply()
    }

    fun read(): Pairing? {
        val encrypted = secret.getString("data", null) ?: return null
        val iv = Base64.decode(secret.getString("iv", ""), Base64.NO_WRAP)
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, iv))
        val o =
            JSONObject(
                String(cipher.doFinal(Base64.decode(encrypted, Base64.NO_WRAP)), Charsets.UTF_8)
            )
        return Pairing(o.getString("endpoint"), o.getString("deviceId"), o.getString("token"))
    }

    fun forget() {
        secret.edit().clear().apply()
    }
}
