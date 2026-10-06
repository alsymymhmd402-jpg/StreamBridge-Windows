# StreamBridge Windows v1.4.0

واجهة Windows عربية موحّدة لبث مصادر TikTok وRTSP/HLS إلى كاميرا UnityCapture المتوافقة مع TikTok LIVE Studio.

## ما الجديد في v1.4.0

- واجهة عربية كاملة بتخطيط RTL بصري: لوحة التحكم، المعاينة، التأثيرات، الحالة، السجل، ورسائل التشغيل.
- لوحة موحّدة تجمع إطار الهاتف العمودي 9:16 مع أدوات السطوع والتباين ودرجة اللون والسرعة ونبرة الصوت ومستوى الصوت.
- أزرار بدء وإيقاف وتشغيل المعاينة خارج الفيديو، مع مؤشر مستقل لاتصال UnityCapture.
- المعاينة لا تجمد الواجهة أثناء فحص الكاميرا أو استخراج رابط TikTok؛ جميع العمليات الثقيلة تعمل في خيوط خلفية.
- أيقونات SVG/PNG مخصصة وملف `streambridge.ico` مضمّن في EXE.
- المعاينة تملأ إطار الهاتف بقص مركزي بلا أشرطة سوداء، بينما يبقى إخراج الكاميرا الأصلي مستقلًا.

## تثبيت UnityCapture

استخدم الحزمة الرسمية فقط: [تحميل UnityCapture ZIP](https://github.com/schellingb/UnityCapture/archive/refs/heads/master.zip). بعد فك الضغط شغّل `Install\\Install.bat` عبر **Run as administrator**. يجب أن تبقى ملفات DLL بجانب الملف. [التعليمات الرسمية](https://github.com/schellingb/UnityCapture).

## البناء والاختبار

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\\build_windows.ps1 -Mode onefile
```

يشغّل البناء الاختبارات الآلية ويضمّن الأيقونات داخل EXE. نجاح CI لا يغني عن اختبار UnityCapture وTikTok LIVE Studio على جهاز Windows فعلي.
