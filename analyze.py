"""
Song analysis: tempo, beats, structural sections, energy, key.
"""
import numpy as np
import librosa
import librosa.segment


NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

# Krumhansl-Schmuckler key profiles
MAJOR_PROFILE = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
MINOR_PROFILE = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])


def load_audio(path, sr=22050):
    y, sr = librosa.load(path, sr=sr, mono=True)
    duration = librosa.get_duration(y=y, sr=sr)
    return y, sr, duration


def analyze_tempo_and_beats(y, sr):
    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
    tempo = float(np.atleast_1d(tempo)[0])
    beat_times = librosa.frames_to_time(beat_frames, sr=sr)
    return tempo, beat_times


def refine_tempo_octave(y, sr, tempo, hop_length=512):
    """librosa's beat tracker sometimes locks onto double or half the
    perceptual tempo. Compare onset-envelope autocorrelation strength at
    the detected tempo vs half tempo and prefer whichever is a stronger,
    more plausible pulse (favoring the slower candidate if it's close)."""
    onset_env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop_length)
    ac = librosa.autocorrelate(onset_env, max_size=len(onset_env))
    frame_rate = sr / hop_length

    def strength_at(bpm):
        lag = int(round(60.0 / bpm * frame_rate))
        lag = max(1, min(lag, len(ac) - 1))
        return ac[lag]

    s_full = strength_at(tempo)
    half = tempo / 2.0
    if half >= 50:
        s_half = strength_at(half)
        if s_half > s_full * 0.9:
            return half
    return tempo


def analyze_key(y, sr):
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
    chroma_mean = chroma.mean(axis=1)
    best_score, best_key, best_mode = -1e9, 0, 'major'
    for shift in range(12):
        maj = np.roll(MAJOR_PROFILE, shift)
        minr = np.roll(MINOR_PROFILE, shift)
        maj_score = np.corrcoef(chroma_mean, maj)[0, 1]
        min_score = np.corrcoef(chroma_mean, minr)[0, 1]
        if maj_score > best_score:
            best_score, best_key, best_mode = maj_score, shift, 'major'
        if min_score > best_score:
            best_score, best_key, best_mode = min_score, shift, 'minor'
    return f"{NOTE_NAMES[best_key]} {best_mode}"


def energy_curve(y, sr, hop_length=512):
    rms = librosa.feature.rms(y=y, hop_length=hop_length)[0]
    times = librosa.frames_to_time(np.arange(len(rms)), sr=sr, hop_length=hop_length)
    # normalize 0-1
    rms_norm = (rms - rms.min()) / (np.ptp(rms) + 1e-9)
    return times, rms_norm


def detect_sections(y, sr, n_sections=None):
    """
    Structural segmentation using a self-similarity recurrence matrix on
    MFCC+chroma features, agglomerative clustering into labeled sections.
    Returns list of (start_time, end_time, label) where label is a cluster id
    (relabeled later into intro/verse/chorus/etc by energy ranking).
    """
    hop_length = 512
    mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13, hop_length=hop_length)
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=hop_length)
    features = np.vstack([mfcc, chroma])

    # Beat-synchronize features for stability
    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr, hop_length=hop_length)
    if len(beat_frames) < 8:
        # too short / no clear beat - just split into fixed chunks
        duration = librosa.get_duration(y=y, sr=sr)
        n = max(3, int(duration // 20))
        bounds = np.linspace(0, duration, n + 1)
        return [(bounds[i], bounds[i + 1], i % 3) for i in range(n)]

    beat_features = librosa.util.sync(features, beat_frames, aggregate=np.median)

    duration = librosa.get_duration(y=y, sr=sr)
    n_boundary_frames = beat_features.shape[1]
    target_by_duration = max(4, int(duration // 12))
    k = n_sections or max(4, min(28, min(target_by_duration, n_boundary_frames // 3)))

    bound_beats = librosa.segment.agglomerative(beat_features, k)
    bound_frames = beat_frames[np.clip(bound_beats, 0, len(beat_frames) - 1)]
    bound_times = librosa.frames_to_time(bound_frames, sr=sr, hop_length=hop_length)
    bound_times = sorted(set([0.0] + list(bound_times) + [librosa.get_duration(y=y, sr=sr)]))

    # Cluster each segment's mean feature to assign a repeating-pattern label
    seg_vectors = []
    for i in range(len(bound_times) - 1):
        t0, t1 = bound_times[i], bound_times[i + 1]
        f0 = librosa.time_to_frames(t0, sr=sr, hop_length=hop_length)
        f1 = librosa.time_to_frames(t1, sr=sr, hop_length=hop_length)
        f1 = max(f1, f0 + 1)
        seg_vectors.append(features[:, f0:f1].mean(axis=1))
    seg_vectors = np.array(seg_vectors)

    from sklearn.cluster import AgglomerativeClustering
    n_clusters = min(len(seg_vectors), max(2, k // 2))
    if len(seg_vectors) > 1:
        labels = AgglomerativeClustering(n_clusters=n_clusters).fit_predict(seg_vectors)
    else:
        labels = [0]

    sections = []
    for i in range(len(bound_times) - 1):
        sections.append((bound_times[i], bound_times[i + 1], int(labels[i])))
    return sections


def merge_short_sections(sections, min_duration=3.0):
    """Merge sections shorter than min_duration into the following section
    (or the previous one if it's the last)."""
    if not sections:
        return sections
    merged = [dict(s) for s in sections]
    i = 0
    while i < len(merged):
        dur = merged[i]["end"] - merged[i]["start"]
        if dur < min_duration and len(merged) > 1:
            if i < len(merged) - 1:
                merged[i + 1]["start"] = merged[i]["start"]
                del merged[i]
            else:
                merged[i - 1]["end"] = merged[i]["end"]
                del merged[i]
                i -= 1
        else:
            i += 1
    return merged


def label_sections_semantically(sections, times, energy):
    """
    Turn cluster ids into intro/verse/chorus/bridge/outro guesses based on
    position in song + relative energy of the cluster.
    """
    def avg_energy(t0, t1):
        mask = (times >= t0) & (times < t1)
        if not mask.any():
            return 0.0
        return float(energy[mask].mean())

    enriched = []
    for (t0, t1, cluster) in sections:
        enriched.append({"start": t0, "end": t1, "cluster": cluster, "energy": avg_energy(t0, t1)})

    if not enriched:
        return enriched

    cluster_energy = {}
    cluster_counts = {}
    for seg in enriched:
        cluster_energy.setdefault(seg["cluster"], []).append(seg["energy"])
        cluster_counts[seg["cluster"]] = cluster_counts.get(seg["cluster"], 0) + 1
    cluster_avg = {c: np.mean(v) for c, v in cluster_energy.items()}

    # A real chorus repeats (not just loud once) but shouldn't be the
    # dominant backbone texture running through most of the track either -
    # it's typically a hook occupying a minority (~20-45%) of the runtime,
    # with above-average energy. Score repeated clusters (>=2 occurrences)
    # by energy, skipping any that eat up too much of the song; fall back
    # to the single loudest cluster if nothing qualifies.
    total_dur = sum(s["end"] - s["start"] for s in enriched) or 1.0
    cluster_dur = {}
    for seg in enriched:
        cluster_dur[seg["cluster"]] = cluster_dur.get(seg["cluster"], 0.0) + (seg["end"] - seg["start"])
    overall_energy_avg = float(np.mean([s["energy"] for s in enriched]))

    repeated_clusters = [c for c, n in cluster_counts.items() if n >= 2]
    candidates = [
        c for c in repeated_clusters
        if cluster_dur[c] / total_dur <= 0.45 and cluster_avg[c] >= overall_energy_avg
    ]
    if candidates:
        highest_cluster = max(candidates, key=lambda c: cluster_avg[c])
    elif repeated_clusters:
        highest_cluster = max(repeated_clusters, key=lambda c: cluster_avg[c])
    else:
        highest_cluster = max(cluster_avg, key=cluster_avg.get)

    n = len(enriched)
    for i, seg in enumerate(enriched):
        if i == 0:
            seg["label"] = "intro"
        elif i == n - 1:
            seg["label"] = "outro"
        elif seg["cluster"] == highest_cluster:
            seg["label"] = "chorus"
        else:
            seg["label"] = "verse"

    # mark a short low-energy segment right before a chorus as "bridge" if it repeats late
    for i in range(1, n - 1):
        seg = enriched[i]
        if seg["label"] == "verse" and i > n // 2 and (seg["end"] - seg["start"]) < 20:
            prev_labels = [s["label"] for s in enriched[:i]]
            if prev_labels.count("verse") >= 2:
                seg["label"] = "bridge"

    return enriched


def analyze_song(path):
    y, sr, duration = load_audio(path)
    tempo, beat_times = analyze_tempo_and_beats(y, sr)
    tempo = refine_tempo_octave(y, sr, tempo)
    key = analyze_key(y, sr)
    times, energy = energy_curve(y, sr)
    raw_sections = detect_sections(y, sr)
    sections = label_sections_semantically(raw_sections, times, energy)
    sections = merge_short_sections(sections, min_duration=3.0)

    overall_energy = float(energy.mean())
    return {
        "path": path,
        "duration": duration,
        "tempo": round(tempo, 1),
        "key": key,
        "overall_energy": round(overall_energy, 3),
        "sections": [
            {
                "label": s["label"],
                "start": round(s["start"], 2),
                "end": round(s["end"], 2),
                "duration": round(s["end"] - s["start"], 2),
                "energy": round(s["energy"], 3),
            }
            for s in sections
        ],
    }


if __name__ == "__main__":
    import sys, json
    result = analyze_song(sys.argv[1])
    print(json.dumps(result, indent=2))
