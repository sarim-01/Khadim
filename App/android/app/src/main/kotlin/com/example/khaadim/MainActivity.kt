package com.example.khaadim

import android.app.Activity
import android.content.Intent
import android.os.Bundle
import android.speech.RecognizerIntent
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

class MainActivity : FlutterActivity() {

    private val CHANNEL = "com.example.khaadim/speech"
    private val SPEECH_REQUEST_CODE = 101

    private var pendingResult: MethodChannel.Result? = null

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)

        MethodChannel(
            flutterEngine.dartExecutor.binaryMessenger,
            CHANNEL
        ).setMethodCallHandler { call, result ->
            when (call.method) {
                "startSpeech" -> {
                    val locale = call.argument<String>("locale") ?: "en-US"
                    pendingResult = result
                    startNativeSpeechRecognition(locale)
                }
                else -> result.notImplemented()
            }
        }
    }

    private fun startNativeSpeechRecognition(locale: String) {
        val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
            putExtra(
                RecognizerIntent.EXTRA_LANGUAGE_MODEL,
                RecognizerIntent.LANGUAGE_MODEL_FREE_FORM
            )
            putExtra(RecognizerIntent.EXTRA_LANGUAGE, locale)
            putExtra(RecognizerIntent.EXTRA_PROMPT, "Speak now...")
            putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 1)
        }

        try {
            startActivityForResult(intent, SPEECH_REQUEST_CODE)
        } catch (e: Exception) {
            pendingResult?.error(
                "STT_UNAVAILABLE",
                "Speech recognition not available on this device",
                null
            )
            pendingResult = null
        }
    }

    override fun onActivityResult(
        requestCode: Int,
        resultCode: Int,
        data: Intent?
    ) {
        super.onActivityResult(requestCode, resultCode, data)

        if (requestCode == SPEECH_REQUEST_CODE) {
            if (resultCode == Activity.RESULT_OK && data != null) {
                val results = data.getStringArrayListExtra(
                    RecognizerIntent.EXTRA_RESULTS
                )
                val recognized = results?.firstOrNull() ?: ""
                pendingResult?.success(recognized)
            } else {
                // User cancelled or no result
                pendingResult?.success("")
            }
            pendingResult = null
        }
    }
}