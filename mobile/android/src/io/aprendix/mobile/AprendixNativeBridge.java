package io.aprendix.mobile;

import android.app.AlarmManager;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.content.pm.ActivityInfo;
import android.os.Build;
import android.os.VibrationEffect;
import android.os.Vibrator;
import org.kivy.android.PythonActivity;
import android.net.Uri;
import com.google.android.gms.tasks.Tasks;
import com.google.mlkit.vision.common.InputImage;
import com.google.mlkit.vision.text.Text;
import com.google.mlkit.vision.text.TextRecognition;
import com.google.mlkit.vision.text.latin.TextRecognizerOptions;
import java.io.File;
import javax.crypto.Cipher;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;

public final class AprendixNativeBridge {
    public static void setEditorLandscape(boolean enabled) {
        PythonActivity.mActivity.setRequestedOrientation(
            enabled
                ? ActivityInfo.SCREEN_ORIENTATION_SENSOR_LANDSCAPE
                : ActivityInfo.SCREEN_ORIENTATION_UNSPECIFIED
        );
    }

    public static byte[] aesGcmEncrypt(byte[] key, byte[] nonce, byte[] plaintext, byte[] aad) throws Exception {
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, new SecretKeySpec(key, "AES"), new GCMParameterSpec(128, nonce));
        cipher.updateAAD(aad);
        return cipher.doFinal(plaintext);
    }
    public static byte[] aesGcmDecrypt(byte[] key, byte[] nonce, byte[] ciphertext, byte[] aad) throws Exception {
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE, new SecretKeySpec(key, "AES"), new GCMParameterSpec(128, nonce));
        cipher.updateAAD(aad);
        return cipher.doFinal(ciphertext);
    }
    public static String ocrFile(String path) throws Exception {
        Context context = PythonActivity.mActivity;
        InputImage image = InputImage.fromFilePath(context, Uri.fromFile(new File(path)));
        Text result = Tasks.await(TextRecognition.getClient(TextRecognizerOptions.DEFAULT_OPTIONS).process(image));
        return result.getText();
    }
    public static void haptic(String pattern) {
        Context context = PythonActivity.mActivity;
        Vibrator vibrator = (Vibrator) context.getSystemService(Context.VIBRATOR_SERVICE);
        if (vibrator == null || !vibrator.hasVibrator()) return;
        long[] timings = pattern.equals("error") ? new long[]{0, 45, 60, 45} : new long[]{0, pattern.equals("success") ? 55 : 25};
        if (Build.VERSION.SDK_INT >= 26) vibrator.vibrate(VibrationEffect.createWaveform(timings, -1));
        else vibrator.vibrate(timings, -1);
    }

    public static boolean schedule(String identifier, long epochMillis, String title, String body) {
        Context context = PythonActivity.mActivity;
        Intent intent = new Intent(context, AprendixReminderReceiver.class);
        intent.putExtra("title", title).putExtra("body", body).putExtra("identifier", identifier);
        PendingIntent pending = PendingIntent.getBroadcast(
            context, identifier.hashCode(), intent,
            PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        AlarmManager alarms = (AlarmManager) context.getSystemService(Context.ALARM_SERVICE);
        if (alarms == null) return false;
        alarms.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, epochMillis, pending);
        return true;
    }
}
