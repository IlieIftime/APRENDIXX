package io.aprendix.mobile;

import android.app.AlarmManager;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.os.Build;
import android.os.VibrationEffect;
import android.os.Vibrator;
import org.kivy.android.PythonActivity;

public final class AprendixNativeBridge {
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
