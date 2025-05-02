try:
    import CLI
except:
    import CLI_fall_back as CLI
import os
import adb
import gameInformation as GI
import phiresource as PS
import configparser


if CLI.SclectBox("请提供安装包","Edition V0.1",(("1.我没有安装包(ADB SHELL 提取)",1,"此操作须在电脑操作，且手机必须为安卓系统，开启USB调试并用正确方法链接"),("2.我有安装包(+obb文件)",2,"TapTap安装包并没有，OBB文件仅限Google Play版本，两种渠道均可"))).start()[1] == 1:
    input("即将初始化adb...\n回车以继续")
    device = adb.ADBController()
    if CLI.SclectBox("选择链接方式","",(("有线连接",1,"需要使用数据线,速度较快,使用时请关闭无线调试"),("无线连接(暂时不可用)",2,"不建议,速度较慢\nNote:对于Android 11+,请先输入'IP地址和端口'内容"))).start()[1] == 1:
        try:
            device.verify_usb_connection()
        except Exception as e:
            print(e)
            device.debug_connection()
    else:

        host = input("输入ip:\n> ")
        port = int(input("输入端口号:\n> "))
        try:
            device.smart_connect(host,port)
        except:
            print("请打开配对码界面,重新输入\n注意:上述内容可能已经改变,输入时请勿退出")
            device.smart_connect(
                host, 
                port,
                pair_port=int(input("输入配对端口号:\n注意:输入的是配对码下方的小字冒号后面的\n> ")), 
                pairing_code=input(f"输入{host}:{port}的配对码:\n> ")
            )
    if CLI.SclectBox("选择渠道","",(("Googly Play",1,"此方法耗时较长，耐心等待"),("TapTap / apk 直接安装",2,"一般就是这个"))).start()[1] == 1:
        device.execute_raw("adb pull \"/storage/emulated/0/Android/obb/com.PigeonGames.Phigros/main.*.com.PigeonGames.Phigros.obb\" "+os.path.abspath("./Phigros.obb"))
        have_obb = True
        obb_path = os.path.abspath("./Phigros.obb")

    res = device.execute_raw("adb shell pm path com.PigeonGames.Phigros ")
    device.execute_raw("adb pull "+ res['stdout'][8:] +" "+os.path.abspath("./Phigros.apk"))
    apk_path = os.path.abspath("./Phigros.apk")
    # 手动断开所有连接
    device.disconnect_all()
else:
    input("Choose apk and obb file(s).\nIf you don't have obb file , you just need to choose the apk file.\nPress Enter to cintinue...")
    paths = CLI.FileOpenBox(os.getcwd(),multi=True).start()
    for i in paths:
        if i[-4:] == ".obb":
            obb_path = i
        elif i[-4:] == ".apk" :
            apk_path = i
try:
    print("OBB file:",obb_path)
    have_obb=True
except:
    print("You don't select OBB file!")
    have_obb=False
print("APK file:",apk_path)
if not os.path.isdir("info"):
    os.mkdir("info")
print("Updating data...")
GI.run(apk_path)
res = CLI.SclectBox("选择解压部分",
    "Note:Illustration music Chart",
    (
        ("Avatar",0,"角色头像"),
        ("Chart",1,"铺面文件"),
        ("IllustrationBlur",2,"模糊曲绘"),
        ("IllustrationLowRes",3,"低质量曲绘"),
        ("Illustration",4,"曲绘"),
        ("Music",5,"音乐")
    ),
    multi=True
).start()
chkl = ["false","false","false","false","false","false"]
for i in res:
    chkl[i[1]] = "true"
config = configparser.ConfigParser()
config.read('config.ini',encoding='utf-8')
config.set('TYPES', 'avatar', chkl[0])
config.set('TYPES', 'Chart', chkl[1])
config.set('TYPES', 'IllustrationBlur', chkl[2])
config.set('TYPES', 'IllustrationLowRes', chkl[3])
config.set('TYPES', 'Illustration', chkl[4])
config.set('TYPES', 'music', chkl[5])
with open('config.ini', 'w', encoding='utf-8') as f:
    config.write(f)
if have_obb:
    PS.main(obb_path)
else:
    PS.main(apk_path)

import phira