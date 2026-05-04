init -999 python:
    import sys
    renpy.log("KOKORO PROBE: ai_tts_kokoro.rpy loaded")
    renpy.log("KOKORO PROBE: python = %r" % sys.version)


init 999 python:
    import os
    import re
    import json
    import hashlib

    try:
        import threading
    except Exception:
        threading = None

    try:
        from urllib import request as urllib_request
    except ImportError:
        import urllib2 as urllib_request

    try:
        text_type = unicode
    except NameError:
        text_type = str

    try:
        _kokoro_state_base = NoRollback
    except NameError:
        _kokoro_state_base = object

    renpy.log("KOKORO TTS: init block reached")

    KOKORO_ENABLED = True
    KOKORO_URL = "http://127.0.0.1:8880/v1/audio/speech"
    KOKORO_MODEL = "kokoro"
    KOKORO_RESPONSE_FORMAT = "mp3"
    KOKORO_SPEED = 1.0
    KOKORO_TIMEOUT = 20
    KOKORO_CACHE_VERSION = "kokoro-self-voicing-v1"

    KOKORO_CHANNEL = "kokoro"
    KOKORO_CACHE_DIR_NAME = "tts_cache_kokoro"
    KOKORO_DEFAULT_VOICE = "af_bella"

    # Speaker name reading mode.
    # Options:
    # "always" = read the speaker name before every line.
    # "never" = never read speaker names.
    # "on_speaker_change" = read the name only when the speaker changes.
    KOKORO_READ_SPEAKER_NAMES = "on_speaker_change"

    # False stores generated audio in Ren'Py's save/user area when possible.
    # True stores generated audio in game/tts_cache_kokoro when possible.
    KOKORO_STORE_AUDIO_IN_GAME_DIR = False

    KOKORO_VOICE_BY_SPEAKER = {
        "Narrator": "af_heart",
        "MC": "am_adam",
        "Daniel": "am_adam",
        "Stacy": "af_bella",
        "Min": "af_sarah",
        "Lydia": "af_heart",
    }


    class KokoroTTSState(_kokoro_state_base):
        def __init__(self):
            self.worker_started = False
            self.request_id = 0
            self.active_id = 0
            self.pending = None
            self.last_speech_mode = None
            self.last_spoken_speaker = None
            self.pending_speaker = None

            if threading is not None:
                self.lock = threading.RLock()
                self.condition = threading.Condition(self.lock)
            else:
                self.lock = None
                self.condition = None


    _kokoro_state = KokoroTTSState()


    def kokoro_to_text(value):
        if value is None:
            return u""

        try:
            return text_type(value)
        except Exception:
            try:
                return str(value)
            except Exception:
                return u""


    def kokoro_clean_text(text):
        text = kokoro_to_text(text)

        if not text:
            return u""

        text = re.sub(r"\{[^}]*\}", "", text)
        text = text.replace("[", "").replace("]", "")
        text = re.sub(r"\s+", " ", text)

        return text.strip()


    def kokoro_self_voicing_mode():
        try:
            return renpy.game.preferences.self_voicing
        except Exception:
            return False


    def kokoro_speech_mode_active():
        mode = kokoro_self_voicing_mode()
        return mode is True or mode == True


    def kokoro_sorted_speakers():
        speakers = []

        for speaker in KOKORO_VOICE_BY_SPEAKER.keys():
            name = kokoro_clean_text(speaker)

            if name:
                speakers.append(name)

        return sorted(speakers, key=len, reverse=True)


    def kokoro_name_read_mode():
        mode = KOKORO_READ_SPEAKER_NAMES

        if mode is True:
            return "always"

        if mode is False or mode is None:
            return "never"

        mode_text = kokoro_clean_text(mode).lower().replace("_", " ").replace("-", " ")

        if mode_text in ("true", "yes", "always", "on"):
            return "always"

        if mode_text in ("false", "no", "never", "off"):
            return "never"

        if mode_text in (
            "on speaker change",
            "on speaker changes",
            "on speaker changed",
            "on speakerchange",
            "onspeakerchange",
            "speaker change",
            "speaker changes",
            "when speaker changes",
            "when the speaker changes",
            "when it changes",
            "when changes",
            "on change",
            "change",
            "changes",
        ):
            return "change"

        renpy.log("KOKORO TTS: unknown KOKORO_READ_SPEAKER_NAMES value %r, using 'on_speaker_change'" % mode)
        return "change"


    def kokoro_known_speaker_match(clean):
        for speaker in kokoro_sorted_speakers():
            if clean == speaker:
                return speaker, u""

            if not clean.startswith(speaker):
                continue

            rest = clean[len(speaker):]
            stripped = rest.lstrip()

            if not stripped:
                continue

            if stripped[0] in (":", ".", "-"):
                return speaker, kokoro_clean_text(stripped[1:])

            if rest.startswith(" "):
                return speaker, kokoro_clean_text(rest)

        return None, clean


    def kokoro_unknown_speaker_match(clean):
        match = re.match(r"^([^:]{1,40}):\s+(.+)$", clean)

        if match:
            speaker = kokoro_clean_text(match.group(1))
            body = kokoro_clean_text(match.group(2))

            if speaker and body:
                return speaker, body

        match = re.match(r"^(.{1,40}?)\s+-\s+(.+)$", clean)

        if match:
            speaker = kokoro_clean_text(match.group(1))
            body = kokoro_clean_text(match.group(2))

            if speaker and body:
                return speaker, body

        return None, clean


    def kokoro_split_speaker_text(text):
        clean = kokoro_clean_text(text)

        if not clean:
            return None, u""

        speaker, body = kokoro_known_speaker_match(clean)

        if speaker is not None:
            return speaker, body

        return kokoro_unknown_speaker_match(clean)


    def kokoro_voice_for_speaker(speaker):
        if speaker:
            voice = KOKORO_VOICE_BY_SPEAKER.get(speaker, None)

            if voice is not None:
                return voice

            for speaker_name, mapped_voice in KOKORO_VOICE_BY_SPEAKER.items():
                if kokoro_clean_text(speaker_name) == speaker:
                    return mapped_voice

        return KOKORO_DEFAULT_VOICE


    def kokoro_apply_name_policy(speaker, body):
        state = _kokoro_state
        mode = kokoro_name_read_mode()
        read_name = False

        if mode == "always":
            read_name = True
        elif mode == "change":
            read_name = speaker != state.last_spoken_speaker

        state.last_spoken_speaker = speaker

        if read_name:
            if body:
                speech_text = speaker + ". " + body
            else:
                speech_text = speaker
        else:
            speech_text = body

        return kokoro_clean_text(speech_text), kokoro_voice_for_speaker(speaker), speaker


    def kokoro_prepare_text_and_voice(text):
        state = _kokoro_state
        clean = kokoro_clean_text(text)
        speaker, body = kokoro_split_speaker_text(clean)

        if speaker is not None:
            if not body:
                state.pending_speaker = speaker
                return u"", kokoro_voice_for_speaker(speaker), speaker

            state.pending_speaker = None
            return kokoro_apply_name_policy(speaker, body)

        if state.pending_speaker is not None:
            speaker = state.pending_speaker
            state.pending_speaker = None
            return kokoro_apply_name_policy(speaker, clean)

        state.last_spoken_speaker = None
        return clean, KOKORO_DEFAULT_VOICE, None


    def kokoro_cache_key(text, voice, speed):
        raw = u"%s|%s|%s|%s|%s|%s" % (
            KOKORO_CACHE_VERSION,
            KOKORO_URL,
            KOKORO_MODEL,
            voice,
            speed,
            text,
        )

        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


    def kokoro_make_dir(path):
        if not os.path.exists(path):
            os.makedirs(path)

        probe = os.path.join(path, ".write_test")

        with open(probe, "wb") as f:
            f.write(b"ok")

        try:
            os.remove(probe)
        except Exception:
            pass


    def kokoro_select_cache_dir():
        candidates = []

        gamedir = getattr(config, "gamedir", None)
        savedir = getattr(config, "savedir", None)
        basedir = getattr(config, "basedir", None)

        if KOKORO_STORE_AUDIO_IN_GAME_DIR:
            if gamedir:
                candidates.append((
                    os.path.join(gamedir, KOKORO_CACHE_DIR_NAME),
                    KOKORO_CACHE_DIR_NAME,
                ))

            if basedir:
                basedir_cache = os.path.join(basedir, KOKORO_CACHE_DIR_NAME)
                candidates.append((basedir_cache, basedir_cache))

            if savedir:
                savedir_cache = os.path.join(savedir, KOKORO_CACHE_DIR_NAME)
                candidates.append((savedir_cache, savedir_cache))

        else:
            if savedir:
                savedir_cache = os.path.join(savedir, KOKORO_CACHE_DIR_NAME)
                candidates.append((savedir_cache, savedir_cache))

            if basedir:
                basedir_cache = os.path.join(basedir, KOKORO_CACHE_DIR_NAME)
                candidates.append((basedir_cache, basedir_cache))

            if gamedir:
                candidates.append((
                    os.path.join(gamedir, KOKORO_CACHE_DIR_NAME),
                    KOKORO_CACHE_DIR_NAME,
                ))

        for disk_dir, play_prefix in candidates:
            try:
                kokoro_make_dir(disk_dir)
                return disk_dir, play_prefix
            except Exception as e:
                renpy.log("KOKORO TTS: cache dir unavailable %r: %r" % (disk_dir, e))

        raise Exception("KOKORO TTS: no writable cache directory")


    TTS_CACHE_DIR, TTS_CACHE_PLAY_PREFIX = kokoro_select_cache_dir()
    renpy.log("KOKORO TTS: cache dir = %r" % TTS_CACHE_DIR)


    def kokoro_play_name(filename):
        if TTS_CACHE_PLAY_PREFIX == KOKORO_CACHE_DIR_NAME:
            value = os.path.join(TTS_CACHE_PLAY_PREFIX, filename)
        else:
            value = os.path.join(TTS_CACHE_DIR, filename)

        return value.replace("\\", "/")


    def kokoro_fetch_audio(text, voice, speed):
        payload = {
            "model": KOKORO_MODEL,
            "input": text,
            "voice": voice,
            "response_format": KOKORO_RESPONSE_FORMAT,
            "speed": speed,
        }

        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")

        req = urllib_request.Request(
            KOKORO_URL,
            data=data,
            headers={
                "Content-Type": "application/json",
            }
        )

        response = urllib_request.urlopen(req, timeout=KOKORO_TIMEOUT)

        try:
            return response.read()
        finally:
            try:
                response.close()
            except Exception:
                pass


    def kokoro_get_audio_file(text, voice, speed):
        key = kokoro_cache_key(text, voice, speed)
        filename = key + "." + KOKORO_RESPONSE_FORMAT
        path = os.path.join(TTS_CACHE_DIR, filename)

        if os.path.exists(path) and os.path.getsize(path) > 0:
            renpy.log("KOKORO TTS: cache HIT | %r" % path)
            return kokoro_play_name(filename), key

        renpy.log("KOKORO TTS: cache MISS | voice=%r | text=%r" % (voice, text))

        audio = kokoro_fetch_audio(text, voice, speed)

        if not audio:
            raise Exception("Kokoro returned no audio data")

        tmp_path = path + ".tmp"

        with open(tmp_path, "wb") as f:
            f.write(audio)

        os.rename(tmp_path, path)

        renpy.log("KOKORO TTS: saved %r (%d bytes)" % (path, len(audio)))

        return kokoro_play_name(filename), key


    def kokoro_pump_audio():
        try:
            pump = getattr(renpy.music, "pump", None)

            if pump is not None:
                pump()
        except Exception as e:
            renpy.log("KOKORO TTS: audio pump failed: %r" % e)


    def kokoro_stop_playback(reason):
        try:
            renpy.music.stop(channel=KOKORO_CHANNEL, fadeout=0)
            kokoro_pump_audio()
            renpy.log("KOKORO TTS: stopped playback | %s" % reason)
        except Exception as e:
            renpy.log("KOKORO TTS: stop failed | %s | %r" % (reason, e))


    def kokoro_cancel_and_stop(reason, reset_speaker=False):
        state = _kokoro_state

        if state.condition is not None:
            with state.condition:
                state.request_id += 1
                state.active_id = state.request_id
                state.pending = None
                state.condition.notify()

        if reset_speaker:
            state.last_spoken_speaker = None
            state.pending_speaker = None

        kokoro_stop_playback(reason)


    def kokoro_play_ready(request_id, play_name, text):
        state = _kokoro_state

        if not kokoro_speech_mode_active():
            renpy.log("KOKORO TTS: stale audio ignored; self-voicing is off | text=%r" % text)
            return

        if state.condition is not None:
            with state.condition:
                if request_id != state.active_id:
                    renpy.log("KOKORO TTS: stale audio ignored | request=%r active=%r" % (
                        request_id,
                        state.active_id,
                    ))
                    return

        try:
            renpy.music.play(
                play_name,
                channel=KOKORO_CHANNEL,
                loop=False,
                fadeout=0,
            )
            kokoro_pump_audio()
            renpy.log("KOKORO TTS: playback started | %r" % play_name)
        except Exception as e:
            renpy.log("KOKORO TTS ERROR: playback failed | %r | %r" % (play_name, e))


    def kokoro_worker_loop(state):
        renpy.log("KOKORO TTS: worker started")

        while True:
            with state.condition:
                while state.pending is None:
                    state.condition.wait()

                request_id, text, voice, speed = state.pending
                state.pending = None

            try:
                play_name, audio_key = kokoro_get_audio_file(text, voice, speed)
                renpy.invoke_in_main_thread(kokoro_play_ready, request_id, play_name, text)
            except Exception as e:
                renpy.log("KOKORO TTS ERROR: generation failed | request=%r | voice=%r | text=%r | %r" % (
                    request_id,
                    voice,
                    text,
                    e,
                ))


    def kokoro_ensure_worker():
        state = _kokoro_state

        if state.condition is None:
            renpy.log("KOKORO TTS: threading unavailable; cannot run non-blocking TTS")
            return False

        if not hasattr(renpy, "invoke_in_thread") or not hasattr(renpy, "invoke_in_main_thread"):
            renpy.log("KOKORO TTS: Ren'Py thread helpers unavailable; cannot run non-blocking TTS")
            return False

        should_start = False

        with state.condition:
            if not state.worker_started:
                state.worker_started = True
                should_start = True

        if should_start:
            try:
                renpy.invoke_in_thread(kokoro_worker_loop, state)
            except Exception as e:
                with state.condition:
                    state.worker_started = False
                renpy.log("KOKORO TTS: worker start failed: %r" % e)
                return False

        return True


    def kokoro_queue_text(text, voice):
        state = _kokoro_state

        if not kokoro_ensure_worker():
            return

        with state.condition:
            state.request_id += 1
            request_id = state.request_id
            state.active_id = request_id
            state.pending = (request_id, text, voice, KOKORO_SPEED)
            state.condition.notify()

        kokoro_stop_playback("new TTS request")

        renpy.log("KOKORO TTS: queued | request=%r | voice=%r | text=%r" % (
            request_id,
            voice,
            text,
        ))


    def kokoro_tts_function(text):
        if not KOKORO_ENABLED:
            return

        if text is None:
            kokoro_cancel_and_stop("empty TTS request")
            return

        if not kokoro_speech_mode_active():
            kokoro_cancel_and_stop("self-voicing is not in speech mode", reset_speaker=True)
            return

        clean = kokoro_clean_text(text)

        if not clean:
            kokoro_cancel_and_stop("blank TTS request")
            return

        speech_text, voice, speaker = kokoro_prepare_text_and_voice(clean)

        if not speech_text:
            renpy.log("KOKORO TTS: speaker name skipped | speaker=%r | source=%r" % (
                speaker,
                clean,
            ))
            return

        kokoro_queue_text(speech_text, voice)


    def kokoro_watch_self_voicing(*args, **kwargs):
        state = _kokoro_state
        active = kokoro_speech_mode_active()

        if state.last_speech_mode and not active:
            kokoro_cancel_and_stop("self-voicing turned off", reset_speaker=True)

        state.last_speech_mode = active


    try:
        renpy.music.register_channel(
            KOKORO_CHANNEL,
            mixer="voice" if getattr(config, "has_voice", True) else "sfx",
            loop=False,
            stop_on_mute=True,
            tight=False
        )
        renpy.log("KOKORO TTS: kokoro channel registered")
    except Exception as e:
        renpy.log("KOKORO TTS: kokoro channel register skipped/failed: %r" % e)

    try:
        if hasattr(config, "tts_voice_channels") and KOKORO_CHANNEL not in config.tts_voice_channels:
            config.tts_voice_channels.append(KOKORO_CHANNEL)
    except Exception as e:
        renpy.log("KOKORO TTS: could not add tts voice channel: %r" % e)

    try:
        if kokoro_watch_self_voicing not in config.interact_callbacks:
            config.interact_callbacks.append(kokoro_watch_self_voicing)
    except Exception as e:
        renpy.log("KOKORO TTS: interact watcher registration failed: %r" % e)

    try:
        if hasattr(config, "periodic_callbacks") and kokoro_watch_self_voicing not in config.periodic_callbacks:
            config.periodic_callbacks.append(kokoro_watch_self_voicing)
    except Exception as e:
        renpy.log("KOKORO TTS: periodic watcher registration failed: %r" % e)

    config.tts_function = kokoro_tts_function

    renpy.log("KOKORO TTS: config.tts_function patched")
