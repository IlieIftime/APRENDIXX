package io.aprendix.mobile;

import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.os.Build;
import androidx.core.app.NotificationCompat;
import org.kivy.android.PythonActivity;

public final class AprendixReminderReceiver extends BroadcastReceiver {
    private static final String CHANNEL = "aprendix-reviews";

    @Override public void onReceive(Context context, Intent source) {
        NotificationManager manager = (NotificationManager) context.getSystemService(Context.NOTIFICATION_SERVICE);
        if (manager == null) return;
        if (Build.VERSION.SDK_INT >= 26) {
            NotificationChannel channel = new NotificationChannel(CHANNEL, "Revisões", NotificationManager.IMPORTANCE_DEFAULT);
            channel.setDescription("Lembretes locais de repetição espaçada");
            manager.createNotificationChannel(channel);
        }
        Intent launch = new Intent(context, PythonActivity.class);
        PendingIntent open = PendingIntent.getActivity(context, 0, launch,
            PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        String title = source.getStringExtra("title");
        String body = source.getStringExtra("body");
        String identifier = source.getStringExtra("identifier");
        manager.notify(identifier == null ? 1 : identifier.hashCode(),
            new NotificationCompat.Builder(context, CHANNEL)
                .setSmallIcon(context.getApplicationInfo().icon)
                .setContentTitle(title == null ? "Aprendix" : title)
                .setContentText(body == null ? "Tens uma revisão local pronta." : body)
                .setContentIntent(open).setAutoCancel(true).build());
    }
}
