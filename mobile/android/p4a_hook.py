"""python-for-android packaging hook for the local reminder receiver."""

from pathlib import Path


def after_apk_build(toolchain) -> None:
    """Harden the rendered manifest and insert the local reminder receiver."""

    manifest = Path(toolchain._dist.dist_dir) / "src" / "main" / "AndroidManifest.xml"
    document = manifest.read_text(encoding="utf-8")
    if 'xmlns:tools="http://schemas.android.com/tools"' not in document:
        document = document.replace(
            'xmlns:android="http://schemas.android.com/apk/res/android"',
            'xmlns:android="http://schemas.android.com/apk/res/android"\n'
            '      xmlns:tools="http://schemas.android.com/tools"',
            1,
        )
    # Some transitive Android libraries request networking even though every
    # Aprendix mobile path is local.  Manifest-merger removal rules make the
    # absence enforceable in the final APK rather than merely omitting it from
    # buildozer.spec.
    network_removals = (
        '    <uses-permission android:name="android.permission.INTERNET" '
        'tools:node="remove" />\n'
        '    <uses-permission android:name="android.permission.ACCESS_NETWORK_STATE" '
        'tools:node="remove" />\n'
    )
    if 'android.permission.INTERNET" tools:node="remove"' not in document:
        application_index = document.find("<application")
        if application_index < 0:
            raise RuntimeError("p4a manifest has no application element")
        document = document[:application_index] + network_removals + document[application_index:]
    receiver = (
        '        <receiver android:name="io.aprendix.mobile.AprendixReminderReceiver" '
        'android:exported="false" />\n'
    )
    if "io.aprendix.mobile.AprendixReminderReceiver" not in document:
        marker = "</application>"
        marker_index = document.rfind(marker)
        if marker_index < 0:
            raise RuntimeError("p4a manifest has no application closing tag")
        document = document[:marker_index] + receiver + document[marker_index:]
    manifest.write_text(document, encoding="utf-8")

    gradle = Path(toolchain._dist.dist_dir) / "build.gradle"
    gradle_document = gradle.read_text(encoding="utf-8")
    if 'abiFilters "arm64-v8a"' not in gradle_document:
        gradle_document = gradle_document.replace(
            "    defaultConfig {\n",
            '    defaultConfig {\n        ndk { abiFilters "arm64-v8a" }\n',
            1,
        )
        gradle.write_text(gradle_document, encoding="utf-8")
