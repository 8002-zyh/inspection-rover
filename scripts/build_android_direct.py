"""Build this dependency-free Android client with official SDK tools.

Fallback when Windows Java/Gradle cannot establish its AF_UNIX wakeup pipe.
Does not patch Java, change firewall settings, or download dependencies.
Outputs a locally debug-signed test APK; use Gradle for normal development.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
import zipfile


def build():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', type=Path, default=Path(os.environ.get('ANDROID_HOME',
                        str(Path(os.environ['LOCALAPPDATA']) / 'Android/Sdk'))))
    parser.add_argument('--build-tools', default='36.0.0')
    parser.add_argument('--platform', default='android-36.1')
    args = parser.parse_args()
    repo = Path(__file__).resolve().parent.parent
    destination = repo / 'android/app/build/direct'
    destination.mkdir(parents=True, exist_ok=True)
    # Some Windows SDK native tools cannot open non-ASCII argument paths.
    # Stage only this client's source under a unique ASCII build-cache folder.
    cache = Path(os.environ['LOCALAPPDATA']) / 'InspectionRover/build-cache'
    cache.mkdir(parents=True, exist_ok=True)
    project = Path(tempfile.mkdtemp(prefix='android-', dir=cache))
    shutil.copytree(repo / 'android/app/src', project / 'app/src')
    output = project / 'app/build/direct'
    for name in ('classes', 'generated', 'dex'):
        (output / name).mkdir(parents=True, exist_ok=True)
    tools = args.sdk / 'build-tools' / args.build_tools
    framework = args.sdk / 'platforms' / args.platform / 'android.jar'
    java = Path(shutil.which('java') or '')
    javac = Path(shutil.which('javac') or '')
    if not framework.is_file() or not java.is_file() or not javac.is_file():
        raise SystemExit('Android SDK platform and JDK java/javac are required')

    def run(*command):
        subprocess.run([str(x) for x in command], cwd=project, check=True)

    ET.register_namespace('android', 'http://schemas.android.com/apk/res/android')
    manifest = ET.parse(project / 'app/src/main/AndroidManifest.xml')
    manifest.getroot().set('package', 'cn.rtrc.patrol')
    manifest.find('application').set('{http://schemas.android.com/apk/res/android}debuggable', 'true')
    manifest.write(output / 'AndroidManifest.xml', encoding='utf-8', xml_declaration=True)
    run(tools / 'aapt2.exe', 'compile', '--dir', project / 'app/src/main/res', '-o', output / 'resources.zip')
    run(tools / 'aapt2.exe', 'link', '-o', output / 'resources.apk', '--manifest', output / 'AndroidManifest.xml',
        '-I', framework, '--java', output / 'generated', '--min-sdk-version', '26', '--target-sdk-version', '35',
        '--version-code', '2', '--version-name', '0.1.1', output / 'resources.zip')
    generated = output / 'generated/cn/rtrc/patrol'
    generated.mkdir(parents=True, exist_ok=True)
    (generated / 'BuildConfig.java').write_text('package cn.rtrc.patrol; public final class BuildConfig {'
                                               ' public static final boolean DEBUG=true; }\n', encoding='utf-8')
    sources = sorted((project / 'app/src/main/java').rglob('*.java')) + sorted((output / 'generated').rglob('*.java'))
    run(javac, '-encoding', 'UTF-8', '-source', '17', '-target', '17', '-classpath', framework,
        '-d', output / 'classes', *sources)
    with zipfile.ZipFile(output / 'classes.jar', 'w') as jar:
        for p in sorted((output / 'classes').rglob('*.class')):
            jar.write(p, p.relative_to(output / 'classes').as_posix())
    run(tools / 'd8.bat', '--min-api', '26', '--lib', framework, '--output', output / 'dex', output / 'classes.jar')
    with zipfile.ZipFile(output / 'resources.apk') as resources, zipfile.ZipFile(output / 'unsigned.apk', 'w') as apk:
        for entry in resources.infolist():
            apk.writestr(entry, resources.read(entry.filename))
        for p in sorted((output / 'dex').glob('classes*.dex')):
            apk.write(p, p.name)
        for p in sorted((project / 'app/src/main/assets').rglob('*')):
            if p.is_file(): apk.write(p, 'assets/' + p.relative_to(project / 'app/src/main/assets').as_posix())
    run(tools / 'zipalign.exe', '-f', '-p', '4', output / 'unsigned.apk', output / 'aligned.apk')
    keystore = Path.home() / '.android/debug.keystore'
    if not keystore.is_file():
        raise SystemExit('No standard local Android debug keystore; generate one with Android Studio first')
    artifact = output / 'inspection-rover-0.1.1-debug.apk'
    run(tools / 'apksigner.bat', 'sign', '--ks', keystore, '--ks-key-alias', 'androiddebugkey',
        '--ks-pass', 'pass:android', '--key-pass', 'pass:android', '--out', artifact, output / 'aligned.apk')
    run(tools / 'apksigner.bat', 'verify', '--verbose', artifact)
    run(tools / 'zipalign.exe', '-c', '4', artifact)
    report = dict(artifact=artifact.name, bytes=artifact.stat().st_size,
                  sha256=hashlib.sha256(artifact.read_bytes()).hexdigest(),
                  signed='standard local Android debug key', min_sdk=26, target_sdk=35,
                  toolchain='official SDK aapt2/javac/d8/zipalign/apksigner',
                  installed_on_device=False)
    (output / 'build-report.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    for path in (artifact, output / 'build-report.json', output / 'classes.jar'):
        shutil.copy2(path, destination / path.name)
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    build()
