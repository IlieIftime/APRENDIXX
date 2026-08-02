"""python-for-android packaging hook for the local reminder receiver."""

from pathlib import Path


def after_apk_build(toolchain) -> None:
    """Insert a non-exported receiver after p4a renders its manifest."""

    manifest = Path(toolchain._dist.dist_dir) / "src" / "main" / "AndroidManifest.xml"
    document = manifest.read_text(encoding="utf-8")
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
