"""
OG Studio Video - Windows desktop app.
Analyzes an mp3/wav, builds a scene storyboard, and opens VideoExpress.ai
so you can paste the generated prompts in order.
"""
import os
import json
import sys
import threading
import traceback
import webbrowser
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, simpledialog

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyze import analyze_song
from storyboard import build_storyboard, write_outputs
from videoexpress_automation import setup_project_folder, run_batch, assemble_final_video

APP_TITLE = "OG Studio Video"
VIDEOEXPRESS_URL = "https://app.videoexpress.ai/"


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("780x680")
        self.minsize(720, 600)

        self.audio_path = tk.StringVar()
        self.song_title = tk.StringVar()
        self.artist = tk.StringVar()
        self.out_dir = tk.StringVar(value=os.path.join(os.getcwd(), "output"))
        self.ref_photo_path = tk.StringVar()
        self.ref_photo_library_name = tk.StringVar()
        self.aspect_ratio = tk.StringVar(value="16:9")
        self.last_md_path = None
        self.last_json_path = None

        self._build_ui()

    def _build_ui(self):
        pad = {"padx": 10, "pady": 6}

        frm_file = tk.Frame(self)
        frm_file.pack(fill="x", **pad)
        tk.Label(frm_file, text="Song file (mp3/wav):", width=18, anchor="w").pack(side="left")
        tk.Entry(frm_file, textvariable=self.audio_path).pack(side="left", fill="x", expand=True, padx=5)
        tk.Button(frm_file, text="Browse...", command=self.browse_file).pack(side="left")

        frm_meta = tk.Frame(self)
        frm_meta.pack(fill="x", **pad)
        tk.Label(frm_meta, text="Song title:", width=18, anchor="w").pack(side="left")
        tk.Entry(frm_meta, textvariable=self.song_title).pack(side="left", fill="x", expand=True, padx=5)

        frm_artist = tk.Frame(self)
        frm_artist.pack(fill="x", **pad)
        tk.Label(frm_artist, text="Artist:", width=18, anchor="w").pack(side="left")
        tk.Entry(frm_artist, textvariable=self.artist).pack(side="left", fill="x", expand=True, padx=5)

        frm_out = tk.Frame(self)
        frm_out.pack(fill="x", **pad)
        tk.Label(frm_out, text="Output folder:", width=18, anchor="w").pack(side="left")
        tk.Entry(frm_out, textvariable=self.out_dir).pack(side="left", fill="x", expand=True, padx=5)
        tk.Button(frm_out, text="Browse...", command=self.browse_out_dir).pack(side="left")

        frm_ref = tk.Frame(self)
        frm_ref.pack(fill="x", **pad)
        tk.Label(frm_ref, text="Character ref. image:", width=18, anchor="w").pack(side="left")
        tk.Entry(frm_ref, textvariable=self.ref_photo_path).pack(side="left", fill="x", expand=True, padx=5)
        tk.Button(frm_ref, text="Browse...", command=self.browse_ref_photo).pack(side="left")

        frm_run_opts = tk.Frame(self)
        frm_run_opts.pack(fill="x", **pad)
        tk.Label(frm_run_opts, text="Photo name in library:", width=18, anchor="w").pack(side="left")
        tk.Entry(frm_run_opts, textvariable=self.ref_photo_library_name).pack(side="left", padx=5)
        tk.Label(frm_run_opts, text="(reference image name)",
                 fg="#888").pack(side="left", padx=(0, 10))
        tk.Label(frm_run_opts, text="Aspect:").pack(side="left")
        tk.OptionMenu(frm_run_opts, self.aspect_ratio, "16:9", "9:16").pack(side="left")

        frm_actions = tk.Frame(self)
        frm_actions.pack(fill="x", **pad)
        self.analyze_btn = tk.Button(frm_actions, text="Analyze & Build Storyboard",
                                      command=self.run_analysis, bg="#2d6cdf", fg="white")
        self.analyze_btn.grid(row=0, column=0, sticky="ew", padx=3, pady=4)
        self.open_folder_btn = tk.Button(frm_actions, text="Open Output Folder",
                                          command=self.open_output_folder, state="disabled")
        self.open_folder_btn.grid(row=0, column=1, sticky="ew", padx=3, pady=4)
        self.open_videoexpress_btn = tk.Button(frm_actions, text="Open VideoExpress.ai",
                                                command=self.open_videoexpress)
        self.open_videoexpress_btn.grid(row=0, column=2, sticky="ew", padx=3, pady=4)
        self.setup_project_btn = tk.Button(frm_actions, text="Upload Project Media",
                                            command=self.run_setup_project, bg="#3a9d4e", fg="white")
        self.setup_project_btn.grid(row=1, column=0, sticky="ew", padx=3, pady=4)
        self.run_storyboard_btn = tk.Button(frm_actions, text="Run Storyboard",
                                             command=self.run_storyboard, bg="#d9822b", fg="white")
        self.run_storyboard_btn.grid(row=1, column=1, sticky="ew", padx=3, pady=4)
        self.assemble_btn = tk.Button(frm_actions, text="Combine Scenes + Add Song",
                                       command=self.run_assemble, bg="#7a3ad9", fg="white")
        self.assemble_btn.grid(row=1, column=2, sticky="ew", padx=3, pady=4)
        self.test_scene_btn = tk.Button(frm_actions, text="Test First Scene", command=lambda: self.run_storyboard(first_scene_only=True))
        self.test_scene_btn.grid(row=2, column=1, sticky="ew", padx=3, pady=4)
        for column in range(3):
            frm_actions.columnconfigure(column, weight=1, uniform="actions")

        self.status_label = tk.Label(self, text="Ready.", anchor="w", justify="left", fg="#555", wraplength=680)
        self.status_label.pack(fill="x", padx=10)

        tk.Label(self, text="Storyboard preview:", anchor="w").pack(fill="x", padx=10, pady=(10, 0))
        self.preview = scrolledtext.ScrolledText(self, wrap="word")
        self.preview.pack(fill="both", expand=True, padx=10, pady=10)

    def browse_file(self):
        path = filedialog.askopenfilename(
            title="Select a song",
            filetypes=[("Audio files", "*.mp3 *.wav *.flac *.m4a"), ("All files", "*.*")],
        )
        if path:
            self.audio_path.set(path)
            if not self.song_title.get():
                base = os.path.splitext(os.path.basename(path))[0]
                self.song_title.set(base)

    def browse_out_dir(self):
        path = filedialog.askdirectory(title="Select output folder")
        if path:
            self.out_dir.set(path)

    def browse_ref_photo(self):
        path = filedialog.askopenfilename(
            title="Select a consistent character reference image",
            filetypes=[("Image files", "*.jpg *.jpeg *.png *.gif"), ("All files", "*.*")],
        )
        if path:
            self.ref_photo_path.set(path)
            base = os.path.splitext(os.path.basename(path))[0]
            self.ref_photo_library_name.set(base[:1].upper() + base[1:] if base else base)

    def set_status(self, text):
        self.status_label.config(text=text)
        self.update_idletasks()

    def run_analysis(self):
        path = self.audio_path.get().strip()
        if not path or not os.path.isfile(path):
            messagebox.showerror(APP_TITLE, "Please choose a valid audio file first.")
            return

        self.analyze_btn.config(state="disabled")
        self.open_folder_btn.config(state="disabled")
        self.preview.delete("1.0", "end")
        self.set_status("Analyzing audio... this can take a bit for longer songs.")

        thread = threading.Thread(target=self._analyze_worker, args=(path,), daemon=True)
        thread.start()

    def _analyze_worker(self, path):
        try:
            analysis = analyze_song(path)
            self.set_status("Building storyboard...")
            storyboard = build_storyboard(
                analysis,
                artist=self.artist.get().strip(),
                song_title=self.song_title.get().strip(),
            )
            out_dir = self.out_dir.get().strip() or "output"
            json_path, md_path = write_outputs(storyboard, out_dir)
            self.last_md_path = md_path

            with open(md_path, encoding="utf-8") as f:
                preview_text = f.read()

            self.after(0, self._on_analysis_done, preview_text, json_path, md_path)
        except Exception as e:
            err = traceback.format_exc()
            self.after(0, self._on_analysis_error, str(e), err)

    def _on_analysis_done(self, preview_text, json_path, md_path):
        self.preview.insert("1.0", preview_text)
        self.last_json_path = json_path
        self.last_md_path = md_path
        self.set_status(f"Done. Saved {os.path.basename(json_path)} and {os.path.basename(md_path)}.")
        self.analyze_btn.config(state="normal")
        self.open_folder_btn.config(state="normal")

    def _on_analysis_error(self, msg, full_trace):
        self.set_status("Error during analysis.")
        self.analyze_btn.config(state="normal")
        messagebox.showerror(APP_TITLE, f"Analysis failed:\n{msg}")
        print(full_trace, file=sys.stderr)

    def open_output_folder(self):
        out_dir = self.out_dir.get().strip() or "output"
        out_dir = os.path.abspath(out_dir)
        if os.path.isdir(out_dir):
            os.startfile(out_dir)
        else:
            messagebox.showwarning(APP_TITLE, "Output folder doesn't exist yet.")

    def open_videoexpress(self):
        webbrowser.open(VIDEOEXPRESS_URL)

    def run_setup_project(self):
        title = self.song_title.get().strip()
        if not title:
            messagebox.showerror(APP_TITLE, "Please enter a song title first "
                                             "(it is used as the Media Library folder name).")
            return
        ref_photo = self.ref_photo_path.get().strip() or None
        song = self.audio_path.get().strip() or None
        if ref_photo and not os.path.isfile(ref_photo):
            messagebox.showerror(APP_TITLE, "Character reference image path is not valid.")
            return
        if song and not os.path.isfile(song):
            messagebox.showerror(APP_TITLE, "Song file path is not valid.")
            return
        if not ref_photo and not song:
            messagebox.showwarning(APP_TITLE, "Nothing to upload: choose a song file and/or "
                                                "a character reference image first. The folder "
                                                "will still be created.")

        self.setup_project_btn.config(state="disabled")
        self.set_status("Opening VideoExpress and creating folder " + repr(title) +
                         "... a browser window will open, please leave it alone.")
        thread = threading.Thread(
            target=self._setup_project_worker, args=(title, ref_photo, song), daemon=True
        )
        thread.start()

    def _setup_project_worker(self, title, ref_photo, song):
        try:
            setup_project_folder(title, ref_photo, song)
            self.after(0, self._on_setup_project_done, title)
        except Exception as e:
            err = traceback.format_exc()
            self.after(0, self._on_setup_project_error, str(e), err)

    def _on_setup_project_done(self, title):
        self.setup_project_btn.config(state="normal")
        self.set_status("Done. Folder " + repr(title) + " is ready in VideoExpress Media Library.")

    def _on_setup_project_error(self, msg, full_trace):
        self.setup_project_btn.config(state="normal")
        self.set_status("Error setting up VideoExpress folder.")
        messagebox.showerror(APP_TITLE, "VideoExpress setup failed:\n" + msg)
        print(full_trace, file=sys.stderr)

    def run_storyboard(self, first_scene_only=False):
        title = self.song_title.get().strip()
        if not title:
            messagebox.showerror(APP_TITLE, "Please enter a song title first "
                                             "(it is used as the Media Library folder name).")
            return
        json_path = self.last_json_path
        if not json_path or not os.path.isfile(json_path):
            messagebox.showerror(APP_TITLE, "No storyboard.json found yet. Click "
                                             "\"Analyze & Build Storyboard\" first.")
            return
        ref_photo_name = self.ref_photo_library_name.get().strip()
        if not ref_photo_name:
            messagebox.showerror(APP_TITLE, "Enter the photo name as it appears in the "
                                             "VideoExpress Media Library (auto-filled when "
                                             "you browse for a reference image, or type it in).")
            return
        aspect = self.aspect_ratio.get()
        folder_name = title

        if not messagebox.askyesno(
            APP_TITLE,
            f"This will generate {'the first scene only' if first_scene_only else 'every scene in the storyboard'} using folder "
            f"\"{folder_name}\" and photo \"{ref_photo_name}\" on VideoExpress. This can take "
            f"a while and opens a visible browser window. Continue?",
        ):
            return

        self.run_storyboard_btn.config(state="disabled")
        self.test_scene_btn.config(state="disabled")
        self.set_status(f"Running storyboard on VideoExpress (folder {folder_name!r})... "
                         "a browser window will open, please leave it alone.")
        thread = threading.Thread(
            target=self._run_storyboard_worker,
            args=(json_path, ref_photo_name, aspect, folder_name, first_scene_only),
            daemon=True,
        )
        thread.start()

    def _run_storyboard_worker(self, json_path, ref_photo_name, aspect, folder_name, first_scene_only=False):
        try:
            run_batch(json_path, ref_photo_name, aspect, folder_name=folder_name,
                      end_scene=1 if first_scene_only else None)
            self.after(0, self._on_run_storyboard_done)
        except Exception as e:
            err = traceback.format_exc()
            self.after(0, self._on_run_storyboard_error, str(e), err)

    def _on_run_storyboard_done(self):
        self.run_storyboard_btn.config(state="normal")
        self.test_scene_btn.config(state="normal")
        self.set_status("Done. Check VideoExpress Media Library for render progress.")

    def _on_run_storyboard_error(self, msg, full_trace):
        self.run_storyboard_btn.config(state="normal")
        self.test_scene_btn.config(state="normal")
        self.set_status("Error running storyboard on VideoExpress.")
        messagebox.showerror(APP_TITLE, "VideoExpress run failed:\n" + msg)
        print(full_trace, file=sys.stderr)


    def run_assemble(self):
        title = self.song_title.get().strip()
        if not title:
            messagebox.showerror(APP_TITLE, "Please enter a song title first "
                                             "(it is used as the Media Library folder name).")
            return
        folder_name = title

        if not self.last_json_path:
            messagebox.showerror(APP_TITLE, "Build the storyboard before assembling its clips.")
            return
        with open(self.last_json_path, encoding="utf-8") as f:
            scene_count = len(json.load(f)["scenes"])
        raw_ids = simpledialog.askstring(
            APP_TITLE,
            f"Enter {scene_count} rendered video asset IDs from My AI Videos, "
            "separated by commas, in storyboard order:", parent=self,
        )
        if raw_ids is None:
            return
        video_idents = [value.strip() for value in raw_ids.split(",")]
        if len(video_idents) != scene_count or any(not value.isascii() or not value.isdecimal() for value in video_idents):
            messagebox.showerror(APP_TITLE, f"Enter exactly {scene_count} numeric video asset IDs in scene order.")
            return

        if not messagebox.askyesno(
            APP_TITLE,
            f"This will drag the {scene_count} selected scene clips for \"{folder_name}\" onto the "
            f"timeline in order, then add the song as a second audio track, and save the "
            f"project. Make sure all scene clips have finished rendering in Media Library "
            f"first. A browser window will open -- please leave it alone. Continue?",
        ):
            return

        self.assemble_btn.config(state="disabled")
        self.set_status(f"Assembling scenes + song on VideoExpress (folder {folder_name!r})... "
                         "a browser window will open, please leave it alone.")
        thread = threading.Thread(
            target=self._run_assemble_worker,
            args=(folder_name, video_idents),
            daemon=True,
        )
        thread.start()

    def _run_assemble_worker(self, folder_name, video_idents):
        try:
            assemble_final_video(folder_name, video_idents=video_idents)
            self.after(0, self._on_assemble_done)
        except Exception as e:
            err = traceback.format_exc()
            self.after(0, self._on_assemble_error, str(e), err)

    def _on_assemble_done(self):
        self.assemble_btn.config(state="normal")
        self.set_status("Done. Review the timeline in VideoExpress, then click Export Video when ready.")

    def _on_assemble_error(self, msg, full_trace):
        self.assemble_btn.config(state="normal")
        self.set_status("Error assembling the final video.")
        messagebox.showerror(APP_TITLE, "Assembling scenes + song failed:\n" + msg)
        print(full_trace, file=sys.stderr)


if __name__ == "__main__":
    app = App()
    app.mainloop()
