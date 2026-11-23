@file:OptIn(ExperimentalTvMaterial3Api::class)

package com.nuvio.tv.ui.owner

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.tv.material3.Button
import androidx.tv.material3.ButtonDefaults
import androidx.tv.material3.ExperimentalTvMaterial3Api
import androidx.tv.material3.Text
import com.nuvio.tv.ui.screens.account.InputField
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import java.util.concurrent.TimeUnit

/**
 * Munk Stream: settings, add-ons and account screens are for the owner only.
 * The PIN is checked by the Maerz server (POST /munk-pin); it is not stored in the app,
 * so unpacking the APK does not reveal it. Offline, the gate stays locked.
 */
object OwnerGate {
    var unlocked by mutableStateOf(false)
        private set

    enum class Check { OK, WRONG, BLOCKED, OFFLINE }

    private const val PIN_URL = "https://89-167-20-85.nip.io/munk-pin"
    private val http by lazy {
        OkHttpClient.Builder()
            .connectTimeout(10, TimeUnit.SECONDS)
            .readTimeout(15, TimeUnit.SECONDS)
            .build()
    }

    suspend fun submit(pin: String): Check {
        val clean = pin.trim()
        if (clean.isEmpty() || !clean.all(Char::isDigit)) return Check.WRONG
        val code = withContext(Dispatchers.IO) {
            runCatching {
                val request = Request.Builder()
                    .url(PIN_URL)
                    .header("User-Agent", "MunkStreamTV")
                    .post("""{"pin":"$clean"}""".toRequestBody("application/json".toMediaType()))
                    .build()
                http.newCall(request).execute().use { it.code }
            }.getOrNull()
        } ?: return Check.OFFLINE
        return when (code) {
            200 -> { unlocked = true; Check.OK }
            400, 403 -> Check.WRONG
            429 -> Check.BLOCKED
            else -> Check.OFFLINE
        }
    }

    fun lock() {
        unlocked = false
    }
}

/** Shows [content] only after the owner PIN was entered; otherwise a PIN screen. */
@Composable
fun OwnerGated(onBack: () -> Unit, content: @Composable () -> Unit) {
    if (OwnerGate.unlocked) {
        content()
    } else {
        OwnerPinScreen(onBack = onBack)
    }
}

@Composable
private fun OwnerPinScreen(onBack: () -> Unit) {
    var pin by remember { mutableStateOf("") }
    var message by remember { mutableStateOf<String?>(null) }
    var checking by remember { mutableStateOf(false) }
    val focus = remember { FocusRequester() }
    val scope = rememberCoroutineScope()
    val submit: () -> Unit = {
        if (!checking) {
            checking = true
            message = null
            val typed = pin
            scope.launch {
                val result = OwnerGate.submit(typed)
                checking = false
                pin = ""
                message = when (result) {
                    OwnerGate.Check.OK -> null
                    OwnerGate.Check.BLOCKED -> "Terlalu banyak cubaan. Cuba lagi nanti"
                    OwnerGate.Check.OFFLINE -> "Tak dapat sambung ke server"
                    OwnerGate.Check.WRONG -> "PIN salah"
                }
            }
        }
    }

    BackHandler(onBack = onBack)
    LaunchedEffect(Unit) { runCatching { focus.requestFocus() } }

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(Color(0xFF0D101E)),
        contentAlignment = Alignment.Center
    ) {
        Column(
            modifier = Modifier.width(420.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Text("Owner only", color = Color.White, fontSize = 28.sp, fontWeight = FontWeight.SemiBold)
            Text(if (checking) "Menyemak..." else "Masukkan PIN owner", color = Color.White.copy(alpha = 0.7f), fontSize = 16.sp)
            InputField(
                value = pin,
                onValueChange = { pin = it.filter(Char::isDigit).take(12) },
                placeholder = "PIN",
                keyboardType = KeyboardType.NumberPassword,
                isPassword = true,
                imeAction = ImeAction.Done,
                onImeAction = submit,
                modifier = Modifier.focusRequester(focus)
            )
            Button(
                onClick = submit,
                modifier = Modifier.fillMaxWidth(),
                colors = ButtonDefaults.colors(
                    containerColor = Color.White,
                    focusedContainerColor = Color.White,
                    contentColor = Color.Black,
                    focusedContentColor = Color.Black
                ),
                shape = ButtonDefaults.shape(RoundedCornerShape(16.dp))
            ) {
                Box(Modifier.fillMaxWidth().padding(vertical = 6.dp), contentAlignment = Alignment.Center) {
                    Text("OK", fontWeight = FontWeight.SemiBold)
                }
            }
            Button(
                onClick = onBack,
                modifier = Modifier.fillMaxWidth(),
                shape = ButtonDefaults.shape(RoundedCornerShape(16.dp))
            ) {
                Box(Modifier.fillMaxWidth().padding(vertical = 6.dp), contentAlignment = Alignment.Center) {
                    Text("Kembali")
                }
            }
            message?.let {
                Text(it, color = Color(0xFFFF6E6E), fontSize = 16.sp)
            }
        }
    }
}
