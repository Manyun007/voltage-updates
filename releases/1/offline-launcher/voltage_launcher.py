#!/usr/bin/env python3
"""VOLTAGE local-test client installer and launcher."""
import argparse
import gzip
import hashlib
import json
import msvcrt
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import uuid
from urllib.parse import urlsplit
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE / 'vendor'))
import minecraft_launcher_lib as mcl
import requests

GAME = ROOT / 'client-offline'
JAVA = ROOT / 'runtime' / 'java21' / 'bin' / 'java.exe'
LOCK = json.loads((ROOT / 'pack-lock.json').read_text(encoding='utf-8-sig'))
PACK = ROOT / 'client' / 'Voltage-0.2.0.mrpack'
VERSION = 'neoforge-' + LOCK['neoforge']
LOCAL_MOD = 'voltageclient-1.0.1.jar'
LOCAL_MOD_HASH = '4b5180e6e8545d8eadde0c499009bd8dd253e0def06d1522a836452019d70f1e751c746a98eff78d9f0363b96a667e1542dbca02809d1bd26e18e3f2fedad42d'
OLD_LOCAL_MOD = 'voltageclient-1.0.0.jar'
OLD_LOCAL_MOD_HASH = 'b8d4175ea6418ae2a05d7fdfe171e902acc27d7d08c4f67280a2dd44f6bf55e345583e9d5be4133ee977c1119757b0c7694e90e2273673ddcb8ff6b02f907e43'
AGENT_HASH = '9c7f4343e6c82034958ffb48c14a2cb0c85928be7283103ce17da00c6d5a7b10'

def say(message):
    print(message, flush=True)

def digest(path, algorithm):
    h = hashlib.new(algorithm)
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()

def get_verified(url, target, expected, algorithm='sha512'):
    if not url.startswith('https://'):
        raise ValueError('Only HTTPS downloads are accepted')
    if target.exists():
        if digest(target, algorithm).lower() != expected.lower():
            raise ValueError(f'Existing file does not match the pack; preserved: {target}')
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(target.suffix + '.download')
    try:
        with requests.get(url, stream=True, timeout=(30, 120)) as response:
            response.raise_for_status()
            with temp.open('wb') as stream:
                for block in response.iter_content(1024 * 1024):
                    stream.write(block)
        if digest(temp, algorithm).lower() != expected.lower():
            raise ValueError(f'Incorrect checksum: {target.name}')
        os.replace(temp, target)
    finally:
        temp.unlink(missing_ok=True)

def status(message):
    if not re.fullmatch(r'Download [0-9a-f]{40}', str(message)):
        say(str(message))

def migrate_managed_mods(mod_dir, expected):
    """Back up verified files from the previous release before changing them."""
    inventory = GAME / 'voltage-managed-mods.json'
    if not inventory.exists(): return
    previous = json.loads(inventory.read_text(encoding='utf-8'))
    if not isinstance(previous, dict): raise ValueError('Invalid managed mod inventory; files preserved')
    for name, checksum in previous.items():
        if (not isinstance(name, str) or Path(name).name != name or not name.lower().endswith('.jar')
                or not isinstance(checksum, str) or not re.fullmatch(r'[0-9a-f]{128}', checksum)):
            raise ValueError('Invalid managed mod inventory; files preserved')
        if expected.get(name) == checksum: continue
        old = mod_dir / name
        if not old.exists(): continue
        if not old.is_file() or old.is_symlink() or digest(old, 'sha512') != checksum:
            raise ValueError('Existing managed mod has changed; preserved: ' + name)
        backup_root = GAME / 'previous-managed-mods'
        if backup_root.is_symlink() or backup_root.is_junction():
            raise ValueError('Linked mod backup directory is not allowed')
        backup_root.mkdir(exist_ok=True)
        archive = backup_root / checksum
        if archive.is_symlink() or archive.is_junction():
            raise ValueError('Linked mod backup directory is not allowed')
        archive.mkdir(exist_ok=True)
        backup = archive / name
        if backup.is_symlink() or backup.is_junction() or (backup.exists() and (not backup.is_file() or digest(backup, 'sha512') != checksum)):
            raise ValueError('Previous managed mod backup has changed; preserved: ' + name)
        if not backup.exists(): shutil.copyfile(old, backup)
        old.unlink()

def ensure_java():
    if JAVA.is_file():
        return
    spec = LOCK['windows_java']
    archive_path = ROOT / '.downloads' / spec['name']
    say('Installing Java 21')
    get_verified(spec['url'], archive_path, spec['sha256'], 'sha256')
    runtime = JAVA.parent.parent.parent
    runtime.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='.java-install-', dir=runtime))
    try:
        with zipfile.ZipFile(archive_path) as archive:
            total = 0
            for info in archive.infolist():
                name = info.filename.replace('\\', '/')
                parts = name.split('/')
                if (name.startswith('/') or ':' in name or '..' in parts
                        or stat.S_ISLNK(info.external_attr >> 16)):
                    raise ValueError('Unsafe path in Java archive')
                total += info.file_size
                if total > 2 * 1024 * 1024 * 1024:
                    raise ValueError('Java archive is unexpectedly large')
            archive.extractall(stage)
        folders = [p for p in stage.iterdir() if (p / 'bin' / 'java.exe').is_file()]
        if len(folders) != 1:
            raise ValueError('Unexpected Java package layout')
        target = runtime / 'java21'
        if target.exists():
            raise ValueError('Java target already exists; preserved')
        os.replace(folders[0], target)
    finally:
        shutil.rmtree(stage, ignore_errors=True)

def prepare():
    ensure_java()
    GAME.mkdir(parents=True, exist_ok=True)
    progress = {'setStatus': status}
    say('Installing Minecraft ' + LOCK['minecraft'])
    mcl.install.install_minecraft_version(LOCK['minecraft'], str(GAME), callback=progress)
    neo_json = GAME / 'versions' / VERSION / (VERSION + '.json')
    if not neo_json.is_file():
        installer = ROOT / '.downloads' / LOCK['loader_installer']['filename']
        get_verified(LOCK['loader_installer']['url'], installer, LOCK['loader_installer']['sha512'])
        profiles = GAME / 'launcher_profiles.json'
        if not profiles.exists():
            profiles.write_text('{"profiles":{}}', encoding='utf-8')
        say('Installing NeoForge ' + LOCK['neoforge'])
        with (GAME / 'neoforge-install.log').open('w', encoding='utf-8') as log:
            subprocess.run([str(JAVA), '-jar', str(installer), '--install-client', str(GAME)],
                           cwd=str(GAME), stdout=log, stderr=subprocess.STDOUT, check=True)
    if not neo_json.is_file():
        raise RuntimeError('NeoForge did not create its client profile')
    say('Checking NeoForge libraries and game assets')
    mcl.install.install_minecraft_version(VERSION, str(GAME), callback=progress)
    mods = [m for m in LOCK['mods'] if m['side'] != 'server']
    mod_dir = GAME / 'mods'
    mod_dir.mkdir(exist_ok=True)
    old_mod = mod_dir / OLD_LOCAL_MOD
    if old_mod.exists():
        if digest(old_mod, 'sha512') != OLD_LOCAL_MOD_HASH:
            raise ValueError('Existing VOLTAGE interface mod has changed; preserved')
        backup = GAME / 'previous-voltage-mods'
        backup.mkdir(exist_ok=True)
        old_backup = backup / OLD_LOCAL_MOD
        if old_backup.exists() and digest(old_backup, 'sha512') != OLD_LOCAL_MOD_HASH:
            raise ValueError('Previous VOLTAGE interface backup has changed; preserved')
        if not old_backup.exists(): shutil.copyfile(old_mod, old_backup)
        old_mod.unlink()
    expected = {m['filename']:m['hashes']['sha512'].lower() for m in mods}
    expected[LOCAL_MOD] = LOCAL_MOD_HASH
    migrate_managed_mods(mod_dir, expected)
    extra = [p.name for p in mod_dir.glob('*.jar') if p.name not in expected]
    if extra:
        raise ValueError('Unmanaged mods preserved: ' + ', '.join(extra))
    for index, mod in enumerate(mods, 1):
        say(f"Mod {index}/{len(mods)}: {mod['name']}")
        get_verified(mod['url'], mod_dir / mod['filename'], mod['hashes']['sha512'])
    source_mod = HERE / LOCAL_MOD
    target_mod = mod_dir / LOCAL_MOD
    if not source_mod.is_file() or digest(source_mod, 'sha512') != LOCAL_MOD_HASH:
        raise ValueError('VOLTAGE interface mod is missing or damaged')
    if target_mod.exists() and digest(target_mod, 'sha512') != LOCAL_MOD_HASH:
        raise ValueError('Existing VOLTAGE interface mod has changed; preserved')
    if not target_mod.exists():
        shutil.copyfile(source_mod, target_mod)
    with zipfile.ZipFile(PACK) as archive:
        for name in ('options.txt', 'servers.dat', 'voltage-client.json'):
            target = GAME / name
            data = archive.read('overrides/' + name)
            if not target.exists():
                # Minecraft 1.21 reads servers.dat as an uncompressed NBT file.
                target.write_bytes(gzip.decompress(data) if name == 'servers.dat' and data.startswith(b'\x1f\x8b') else data)
            elif name == 'servers.dat' and target.read_bytes() == data and data.startswith(b'\x1f\x8b'):
                target.write_bytes(gzip.decompress(data))
    inventory = GAME / 'voltage-managed-mods.json'
    draft = GAME / '.voltage-managed-mods.tmp'
    draft.write_text(json.dumps(expected, sort_keys=True), encoding='utf-8')
    os.replace(draft, inventory)
    say('Client preparation complete')

def offline_uuid(name):
    raw = hashlib.md5(('OfflinePlayer:' + name).encode('utf-8')).digest()
    return str(uuid.UUID(bytes=raw, version=3))

def auth_server():
    config = json.loads((HERE / 'endpoint.json').read_text(encoding='utf-8'))
    url = config['auth_url'].rstrip('/')
    parsed = urlsplit(url)
    if parsed.username or parsed.password or parsed.query or parsed.fragment or not parsed.hostname:
        raise ValueError('Invalid account server address')
    if parsed.scheme != 'https' and not (parsed.scheme == 'http' and parsed.hostname in ('127.0.0.1', 'localhost', '::1')):
        raise ValueError('Account server requires HTTPS outside localhost')
    if not parsed.path.endswith('/authlib-injector'):
        raise ValueError('Invalid account server path')
    return url

def server_address():
    config = json.loads((HERE / 'endpoint.json').read_text(encoding='utf-8'))
    address = config['server_address']
    if not isinstance(address, str) or len(address) > 260:
        raise ValueError('Invalid game server address')
    match = re.fullmatch(r'([A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?):([0-9]{1,5})', address)
    if not match or not 1 <= int(match.group(2)) <= 65535:
        raise ValueError('Invalid game server address')
    return address

def authenticate(name, password):
    if not re.fullmatch(r'[A-Za-z0-9_]{3,16}', name) or not 12 <= len(password) <= 256:
        raise ValueError('Неверный ник или пароль')
    url = auth_server()
    body = {'agent':{'name':'Minecraft','version':1}, 'username':name, 'password':password,
            'clientToken':uuid.uuid4().hex, 'requestUser':True}
    response = requests.post(url + '/authserver/authenticate', json=body, timeout=(10, 30), allow_redirects=False)
    if response.status_code != 200:
        raise ValueError('Не удалось войти. Проверьте ник и пароль.')
    data = response.json()
    profile = data.get('selectedProfile') or {}
    if profile.get('name', '').casefold() != name.casefold() or not data.get('accessToken'):
        raise ValueError('Учётная запись не содержит игрового профиля')
    uuid.UUID(profile['id'])
    return url, profile, data['accessToken']

def launch_authenticated(name, password):
    agent = HERE / 'authlib-injector.jar'
    if not agent.is_file() or digest(agent, 'sha256') != AGENT_HASH:
        raise ValueError('Компонент авторизации отсутствует или повреждён')
    prepare()
    url, profile, token = authenticate(name, password)
    password = None
    options = {'username':profile['name'], 'uuid':profile['id'], 'token':token,
        'executablePath':str(JAVA), 'launcherName':'VOLTAGE', 'launcherVersion':'0.2-local',
        'gameDirectory':str(GAME), 'jvmArguments':['-Xms2G','-Xmx6G','-Dfile.encoding=UTF-8',
        '-Dvoltage.address=' + server_address(),
        '-javaagent:' + str(agent) + '=' + url]}
    command = mcl.command.get_minecraft_command(VERSION, str(GAME), options)
    say('Starting VOLTAGE as ' + profile['name'])
    result = subprocess.run(command, cwd=str(GAME))
    if result.returncode:
        raise RuntimeError(f'Minecraft exited with code {result.returncode}')

def launch(name):
    if not re.fullmatch(r'[A-Za-z0-9_]{3,16}', name):
        raise ValueError('Nickname must contain 3–16 Latin letters, numbers or underscores')
    prepare()
    options = {
        'username': name, 'uuid': offline_uuid(name), 'token': '0',
        'executablePath': str(JAVA), 'launcherName': 'VOLTAGE',
        'launcherVersion': '0.1-local', 'gameDirectory': str(GAME),
        'jvmArguments': ['-Xms2G', '-Xmx6G', '-Dfile.encoding=UTF-8'],
    }
    command = mcl.command.get_minecraft_command(VERSION, str(GAME), options)
    say('Starting VOLTAGE as ' + name)
    result = subprocess.run(command, cwd=str(GAME))
    if result.returncode:
        raise RuntimeError(f'Minecraft exited with code {result.returncode}')

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['prepare', 'launch', 'launch-auth', 'uuid'])
    parser.add_argument('--name', default='Manyun')
    args = parser.parse_args()
    if args.action == 'uuid':
        print(offline_uuid(args.name))
        return
    lock = (ROOT / '.game.lock').open('a+b')
    try:
        if lock.tell() == 0: lock.write(b'0'); lock.flush()
        lock.seek(0)
        try: msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as exc: raise RuntimeError('Игра или обновление уже запущены') from exc
        try:
            if args.action == 'prepare': prepare()
            elif args.action == 'launch': launch(args.name)
            else:
                password = sys.stdin.buffer.readline(4097).decode('utf-8').rstrip('\r\n')
                launch_authenticated(args.name, password)
        finally:
            lock.seek(0); msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
    finally:
        lock.close()

if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('VOLTAGE ERROR: ' + str(exc), file=sys.stderr, flush=True)
        sys.exit(1)
