package io.aprendix.mobile;

import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import java.io.File;
import java.nio.file.Files;
import java.nio.file.StandardCopyOption;
import java.security.KeyStore;
import java.security.SecureRandom;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public final class AprendixKeyStoreBridge {
    private static final String ALIAS = "aprendix-fields-kek-v1";

    private static SecretKey key() throws Exception {
        KeyStore store = KeyStore.getInstance("AndroidKeyStore");
        store.load(null);
        if (!store.containsAlias(ALIAS)) {
            KeyGenerator generator = KeyGenerator.getInstance(
                KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore");
            generator.init(new KeyGenParameterSpec.Builder(
                ALIAS, KeyProperties.PURPOSE_ENCRYPT | KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256).build());
            generator.generateKey();
        }
        return ((KeyStore.SecretKeyEntry) store.getEntry(ALIAS, null)).getSecretKey();
    }

    public static synchronized byte[] getOrCreate(String wrappedPath) throws Exception {
        File destination = new File(wrappedPath);
        if (destination.exists()) {
            byte[] envelope = Files.readAllBytes(destination.toPath());
            if (envelope.length < 29 || envelope[0] != 1) throw new SecurityException("invalid key envelope");
            byte[] nonce = new byte[12];
            System.arraycopy(envelope, 1, nonce, 0, 12);
            byte[] ciphertext = new byte[envelope.length - 13];
            System.arraycopy(envelope, 13, ciphertext, 0, ciphertext.length);
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.DECRYPT_MODE, key(), new GCMParameterSpec(128, nonce));
            return cipher.doFinal(ciphertext);
        }
        byte[] dek = new byte[32];
        new SecureRandom().nextBytes(dek);
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, key());
        byte[] ciphertext = cipher.doFinal(dek);
        byte[] envelope = new byte[13 + ciphertext.length];
        envelope[0] = 1;
        System.arraycopy(cipher.getIV(), 0, envelope, 1, 12);
        System.arraycopy(ciphertext, 0, envelope, 13, ciphertext.length);
        destination.getParentFile().mkdirs();
        File temporary = new File(destination.getParentFile(), destination.getName() + ".tmp");
        Files.write(temporary.toPath(), envelope);
        Files.move(temporary.toPath(), destination.toPath(),
            StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING);
        return dek;
    }
}
