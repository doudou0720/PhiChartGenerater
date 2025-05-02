import atexit
from configparser import ConfigParser
import tkinter
import gameInformation
import phiresource

path = tkinter.Entry()
path.pack()

d = {
    "avatar": tkinter.BooleanVar(),
    "chart": tkinter.BooleanVar(),
    "illustrationblur": tkinter.BooleanVar(),
    "illustrationlowres": tkinter.BooleanVar(),
    "illustration": tkinter.BooleanVar(),
    "music": tkinter.BooleanVar()
}

tkinter.Checkbutton(text="头像", variable=d["avatar"]).pack()
tkinter.Checkbutton(text="谱面", variable=d["chart"]).pack()
tkinter.Checkbutton(text="曲绘(模糊)", variable=d["illustrationblur"]).pack()
tkinter.Checkbutton(text="曲绘(低质量)", variable=d["illustrationlowres"]).pack()
tkinter.Checkbutton(text="曲绘", variable=d["illustration"]).pack()
tkinter.Checkbutton(text="音乐", variable=d["music"]).pack()

c = ConfigParser()
c.optionxform = str
c.read("config.ini", "utf8")

for key in c["TYPES"]:
    d[key].set(c["TYPES"].getboolean(key))

def exit_handle():
    for key in c["TYPES"]:
        c["TYPES"][key] = str(d[key].get())
    with open("config.ini", "w", encoding="utf8") as f:
        c.write(f)
atexit.register(exit_handle)

def callback():
    config = {
        "UPDATE": {
            "main_story": 0,
            "side_story": 0,
            "other_song": 0
        }
    }
    for key, value in d.items():
        config[key] = value.get()
    gameInformation.run(path.get())
    phiresource.run(path.get(), config)


tkinter.Button(text="执行", command = callback).pack()
tkinter.mainloop()
