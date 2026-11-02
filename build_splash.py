"""Build-only artwork and early bootloader progress for the Windows splash."""
from pathlib import Path
from PyInstaller.building.splash import Splash


def splash_image(path):
    from PIL import Image, ImageDraw, ImageFont
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (640, 310), "#111613")
    draw = ImageDraw.Draw(image)
    for y in range(310):
        draw.line((0, y, 639, y), fill=(17 + y // 80, 22 + y // 40, 19 + y // 60))
    def font(size, bold=False):
        return ImageFont.truetype("C:/Windows/Fonts/" + ("segoeuib.ttf" if bold else "segoeui.ttf"), size)
    draw.rectangle((0, 0, 639, 309), outline="#354332", width=1)
    draw.polygon([(36, 50), (46, 40), (56, 50), (46, 60)], outline="#c9ef65", width=2)
    draw.text((70, 27), "OG", font=font(34, True), fill="#f3f5ed")
    draw.text((123, 29), "STUDIO", font=font(31), fill="#9fac9c")
    draw.text((244, 29), "VIDEO", font=font(31), fill="#c9ef65")
    draw.text((36, 103), "Your music. In motion.", font=font(32, True), fill="#f3f5ed")
    draw.text((36, 153), "Preparing your creative workspace", font=font(16), fill="#a9b5a4")
    draw.text((36, 267), "Your project files stay saved.", font=font(12), fill="#87977f")
    image.save(path)
    return str(path.resolve())


class StudioSplash(Splash):
    def __init__(self, image, binaries, datas, **options):
        self.archive_files = max(1, len({entry[0] for entry in binaries + datas}))
        super().__init__(image, binaries, datas, **options)

    def generate_script(self):
        script = super().generate_script()
        script += r'''
wm title . "OG Studio Video is opening"
set startup_file_count 0
set startup_started [clock milliseconds]
.root.canvas create rectangle 36 232 604 238 -fill #303c31 -outline {}
.root.canvas create rectangle 36 232 38 238 -fill #c9ef65 -outline {} -tag startup_bar
.root.canvas create text 604 277 -anchor e -fill #87977f -font myFont -text "0s" -tag startup_elapsed
proc startup_tick {} {
    global startup_started
    set seconds [expr {([clock milliseconds] - $startup_started) / 1000}]
    .root.canvas itemconfigure startup_elapsed -text "${seconds}s"
    after 1000 startup_tick
}
proc canvas_text_update {canvas tag _var - -} {
    global startup_file_count
    upvar $_var var
    if {[string match "OGSTART|*" $var]} {
        set parts [split $var |]
        set percent [lindex $parts 1]
        set message [join [lrange $parts 2 end] |]
    } else {
        incr startup_file_count
        set percent [expr {min(64.0, 64.0 * $startup_file_count / __FILE_TOTAL__)}]
        set message "Unpacking app files... file $startup_file_count"
    }
    $canvas itemconfigure $tag -text $message
    $canvas coords startup_bar 36 232 [expr {36 + 568 * $percent / 100.0}] 238
}
set status_text "OGSTART|0|Unpacking app files..."
startup_tick
'''.replace("__FILE_TOTAL__", str(self.archive_files))
        Path(self.script_name).write_text(script, encoding="utf-8")
        return script
