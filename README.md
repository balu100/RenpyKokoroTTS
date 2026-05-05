# Ren'Py Universal Kokoro TTS

## [VibeVoiceVersion](https://github.com/balu100/RenpyVibeVoiceTTS) way better expressions but more resources.

A drop-in Ren'Py script that replaces Ren'Py self-voicing with Kokoro TTS.

Put `ai_tts_kokoro.rpy` into a game's `game/` folder, run a local Kokoro
server, and press `V` in-game to toggle self-voicing. When self-voicing is on,
Ren'Py sends text to this script, the script generates speech through Kokoro,
caches the MP3, and plays it through Ren'Py's voice mixer.

## Requirements

- A Ren'Py game.
- Docker, if you use the Kokoro FastAPI containers below.
- A Kokoro-compatible OpenAI-style speech endpoint running at:

```text
http://127.0.0.1:8880/v1/audio/speech
```

## Start Kokoro

CPU:

```powershell
docker run -p 8880:8880 ghcr.io/remsky/kokoro-fastapi-cpu:latest
```

NVIDIA GPU:

```powershell
docker run --gpus all -p 8880:8880 ghcr.io/remsky/kokoro-fastapi-gpu:latest
```

Leave the container running while you play.

## Install

1. Copy `ai_tts_kokoro.rpy` into the target game's `game/` folder.
2. Start Kokoro.
3. Start the game.
4. Press `V` to enable Ren'Py self-voicing.
5. Press `V` again to turn it off. Current Kokoro playback and pending TTS work
   will be stopped.

## Configuration

Open `ai_tts_kokoro.rpy` and edit the config values near the top of the file.

### Kokoro endpoint

```python
KOKORO_URL = "http://127.0.0.1:8880/v1/audio/speech"
KOKORO_MODEL = "kokoro"
KOKORO_SPEED = 1.0
KOKORO_TIMEOUT = 20
```

Change `KOKORO_URL` if your Kokoro server runs somewhere else.

### Speaker name reading

```python
KOKORO_READ_SPEAKER_NAMES = "on_speaker_change"
```

Options:

```python
KOKORO_READ_SPEAKER_NAMES = "always"
KOKORO_READ_SPEAKER_NAMES = "never"
KOKORO_READ_SPEAKER_NAMES = "on_speaker_change"
```

- `"always"` reads the speaker name before every line.
- `"never"` removes speaker names from spoken dialogue.
- `"on_speaker_change"` reads the speaker name only when the speaker changes.

Example:

```text
Alice: Hello.      -> reads "Alice. Hello."
Alice: Come here.  -> reads "Come here."
Bob: Wait.         -> reads "Bob. Wait."
```

### Audio cache location

```python
KOKORO_STORE_AUDIO_IN_GAME_DIR = False
```

Options:

```python
KOKORO_STORE_AUDIO_IN_GAME_DIR = False
```

Prefer Ren'Py's save/user area for cached MP3 files. This is the safer default
because installed games may not allow writing inside the game folder.

```python
KOKORO_STORE_AUDIO_IN_GAME_DIR = True
```

Prefer `game/tts_cache_kokoro`, keeping generated audio beside the script when
the game folder is writable.

### Default voice

```python
KOKORO_DEFAULT_VOICE = "af_bella"
```

This voice is used when the script cannot identify a speaker or no speaker
mapping exists.

### Speaker voices

```python
KOKORO_VOICE_BY_SPEAKER = {
    "Narrator": "af_heart",
    "MC": "am_adam",
    "Stacy": "af_bella",
    "Min": "af_sarah",
    "Lydia": "af_heart",
}
```

Add or edit names to match the game:

```python
KOKORO_VOICE_BY_SPEAKER = {
    "Narrator": "af_heart",
    "Alice": "af_bella",
    "Bob": "am_adam",
    "Custom Character": "af_sarah",
}
```

Make sure every dictionary entry has a colon between the speaker and voice:

```python
"Custom Character": "af_sarah",
```

Available Kokoro voice IDs:

```text
American English female:
af_heart, af_alloy, af_aoede, af_bella, af_jessica, af_kore,
af_nicole, af_nova, af_river, af_sarah, af_sky

American English male:
am_adam, am_echo, am_eric, am_fenrir, am_liam, am_michael,
am_onyx, am_puck, am_santa

British English female:
bf_alice, bf_emma, bf_isabella, bf_lily

British English male:
bm_daniel, bm_fable, bm_george, bm_lewis

Spanish:
ef_dora, em_alex, em_santa

French:
ff_siwis

Hindi:
hf_alpha, hf_beta, hm_omega, hm_psi

Italian:
if_sara, im_nicola

Japanese:
jf_alpha, jf_gongitsune, jf_nezumi, jf_tebukuro, jm_kumo

Mandarin Chinese:
zf_xiaobei, zf_xiaoni, zf_xiaoxiao, zf_xiaoyi,
zm_yunjian, zm_yunxi, zm_yunxia, zm_yunyang

Brazilian Portuguese:
pf_dora, pm_alex, pm_santa
```

Your running Kokoro server is the final source of truth. To see the voices
available in your current container, open:

```text
http://127.0.0.1:8880/v1/audio/voices
```

Kokoro FastAPI also supports voice mixing, for example:

```python
"Alice": "af_bella+af_sky",
"Bob": "am_michael(2)+am_puck(1)",
```

## How It Works

This script sets Ren'Py's `config.tts_function`, so it only runs when Ren'Py
self-voicing is enabled. It does not patch every dialogue line directly.

Generated audio is requested in a background thread so a slow Kokoro request
does not block the game UI. When the MP3 is ready, it is played through a custom
Ren'Py channel using the `voice` mixer, so the player's voice volume and mute
settings still apply.

The cache key includes the Kokoro URL, model, voice, speed, and spoken text. If
you change engine/model behavior and want to force regeneration, change:

```python
KOKORO_CACHE_VERSION = "kokoro-self-voicing-v1"
```

For example:

```python
KOKORO_CACHE_VERSION = "kokoro-self-voicing-v2"
```

## Troubleshooting

### Nothing happens when pressing `V`

- Make sure `ai_tts_kokoro.rpy` is inside the game's `game/` folder.
- Make sure the game supports Ren'Py self-voicing.
- Check `log.txt` for lines starting with `KOKORO TTS`.

### The game logs Kokoro connection errors

- Make sure the Kokoro container is still running.
- Open `http://127.0.0.1:8880` in a browser to confirm the server responds.
- Check that `KOKORO_URL` matches the server address.

### The first line is slow

That is expected on a cache miss. The script sends text to Kokoro, waits for the
MP3, and then caches it. The same line should be faster next time.

### Voice volume is too low or muted

The script uses Ren'Py's `voice` mixer. Check the game's voice volume and mute
settings.

### Speaker names are still read incorrectly

Ren'Py games format self-voicing text differently. This script detects common
formats like:

```text
Alice: Hello.
Alice. Hello.
Alice - Hello.
```

If a game uses another format, the speaker name may not be detected.

## Notes

- This is meant as a universal drop-in helper, so it avoids editing the target
  game's scripts.
- It depends on Ren'Py self-voicing. Use `V` to control it.
- It expects a local Kokoro server. The script does not start Kokoro by itself.
