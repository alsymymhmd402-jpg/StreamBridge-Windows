# StreamBridge Windows v1.5.2

تطبيق Windows عربي RTL لبث TikTok وRTSP/HLS إلى كاميرا UnityCapture المتوافقة مع TikTok LIVE Studio.

## الصفحات

- **الرئيسية:** إدخال الرابط، زر استخراج الرابط، وحالة الاتصال فقط.
- **المعاينة والمؤثرات:** إطار هاتف 9:16 في اليمين، وأدوات السطوع والتباين ودرجة اللون والسرعة والصوت في اليسار، مع أزرار بدء/إيقاف ومؤشر الكاميرا خارج الفيديو.
- **حالة الكاميرا:** فحص UnityCapture وتشخيص الاتصال.
- **السجلات والتشخيص:** أخطاء الشبكة وFFmpeg ودورة حياة البث.
- **الإعدادات العامة:** الدقة، FPS، اسم الكاميرا، وأجهزة VB-CABLE.

كل صفحة مستقلة وظاهرة في شريط التنقل، ولا يتم دمجها أو إخفاؤها. المعاينة لا توقف الخيوط الخلفية عند غياب UnityCapture أو أثناء استخراج الرابط.

استخراج رابط المشاركة وفحص UnityCapture يعملان في خيوط خلفية مع مؤشر تحميل. يبدأ التطبيق باستخراج الرابط أولًا ثم يفحص الكاميرا، ويعرض أخطاء FFmpeg بدل تجميد الواجهة أو إخفاء سبب الفشل.

يتم الآن تتبع روابط `vt.tiktok.com` و`vm.tiktok.com` أولًا، مع مهلة لا تقل عن 30 ثانية، وUser-Agent حديث وترويسات Referer، ومحاولات إعادة محدودة. لا يبدأ زر تشغيل المعاينة FFmpeg إلا بعد نجاح استخراج رابط M3U8/RTSP.

## UnityCapture

[تحميل الحزمة الرسمية ZIP](https://github.com/schellingb/UnityCapture/archive/refs/heads/master.zip) ثم فك الضغط وتشغيل `Install\\Install.bat` عبر **Run as administrator**. [التعليمات الرسمية](https://github.com/schellingb/UnityCapture).

## البناء

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\\build_windows.ps1 -Mode onefile
```

يشغّل البناء الاختبارات الآلية ويضمّن أيقونات SVG/PNG وملف Windows ICO داخل EXE.
