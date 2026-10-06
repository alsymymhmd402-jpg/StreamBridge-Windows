"""Arabic multi-page RTL-oriented StreamBridge interface."""
from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
import webbrowser

import numpy as np
from PIL import Image, ImageOps, ImageTk

from .audio import list_output_devices
from .camera_check import UNITYCAPTURE_URL, check_unitycapture
from .core import InvalidStreamUrl, validate_stream_url
from .engine import DEFAULT_SETTINGS, StreamBridgeEngine
from .resolver import normalize_input_url, resolve_stream_url

BG="#080B12"; SIDEBAR="#0C111B"; PANEL="#111927"; TEXT="#F4F7FB"; MUTED="#91A0B5"; CYAN="#25F4EE"; PINK="#FE2C55"; GREEN="#38D996"; YELLOW="#F6C75B"; RED="#FF6B7F"; BORDER="#202B3D"


class StreamBridgeApp(tk.Tk):
    def __init__(self, initial_url: str = "") -> None:
        super().__init__()
        self.title("StreamBridge 1.5.3 — كاميرا بث افتراضية")
        try: self.iconbitmap(str(Path(__file__).resolve().parent / "assets" / "streambridge.ico"))
        except tk.TclError: pass
        self.geometry("1440x900"); self.minsize(1180,760); self.configure(bg=BG)
        self.worker: StreamBridgeEngine|None=None; self._photo=None; self._last_display_frame=None; self._extracted_media_url=""; self._extracted_input_url=""; self._preview_requested=False
        self._closing=False; self._resolving=False; self._last_error=False; self._adjustment_after=None
        self._icons={}; self._pages={}; self._nav={}; self._log_lines=[]
        self.preview_var=tk.BooleanVar(value=True); self.url_var=tk.StringVar(value=initial_url)
        self.resolution_var=tk.StringVar(value="720p · 1280 × 720"); self.fps_var=tk.StringVar(value="30 FPS")
        self.camera_name_var=tk.StringVar(value="Unity Video Capture"); self.audio_device_var=tk.StringVar(value="")
        self.audio_devices={}; self.visual_enabled_var=tk.BooleanVar(value=False); self.speed_enabled_var=tk.BooleanVar(value=False); self.audio_enabled_var=tk.BooleanVar(value=False)
        self.brightness_var=tk.DoubleVar(value=0); self.contrast_var=tk.DoubleVar(value=100); self.hue_var=tk.DoubleVar(value=0); self.speed_var=tk.DoubleVar(value=1.0); self.pitch_var=tk.DoubleVar(value=1.0); self.volume_var=tk.DoubleVar(value=80)
        self._last_metrics={"fps":0.0,"frames":0,"signal":"انتظار","resolution":"1280×720","target_fps":30}
        self._load_icons(); self.protocol("WM_DELETE_WINDOW",self._on_close); self._build_ui(); self.after(100,self._refresh_audio_devices); self.after(40,self._poll_worker)

    def _load_icons(self):
        base=Path(__file__).resolve().parent/"assets"/"icons"
        for name in ("dashboard","preview","status","logs","fx","settings"):
            try: self._icons[name]=ImageTk.PhotoImage(Image.open(base/f"{name}.png").convert("RGBA").resize((22,22),Image.Resampling.LANCZOS))
            except (OSError,tk.TclError): pass

    def _build_ui(self):
        self.grid_columnconfigure(0,weight=0); self.grid_columnconfigure(1,weight=1); self.grid_rowconfigure(0,weight=1)
        self._build_sidebar(); main=tk.Frame(self,bg=BG); main.grid(row=0,column=1,sticky="nsew"); main.grid_columnconfigure(0,weight=1); main.grid_rowconfigure(1,weight=1)
        header=tk.Frame(main,bg=BG); header.grid(row=0,column=0,sticky="ew",padx=28,pady=(20,12)); header.grid_columnconfigure(0,weight=1)
        tk.Label(header,text="STREAMBRIDGE · لوحة البث",bg=BG,fg=TEXT,font=("Segoe UI",20,"bold"),anchor="e").grid(row=0,column=0,sticky="e")
        tk.Label(header,text="واجهة عربية RTL · كاميرا Windows افتراضية",bg=BG,fg=MUTED,font=("Segoe UI",10),anchor="e").grid(row=1,column=0,sticky="e",pady=(3,0))
        self.status_chip=tk.Label(header,text="الحالة  متوقف",bg="#172233",fg=MUTED,font=("Segoe UI",9,"bold"),padx=15,pady=9); self.status_chip.grid(row=0,column=1,rowspan=2,sticky="w",padx=(18,0))
        self.loading=ttk.Progressbar(header,mode="indeterminate",length=130); self.loading.grid(row=0,column=2,rowspan=2,sticky="w",padx=(12,0)); self.loading.stop()
        self.page_stack=tk.Frame(main,bg=BG); self.page_stack.grid(row=1,column=0,sticky="nsew",padx=28,pady=(0,24)); self.page_stack.grid_rowconfigure(0,weight=1); self.page_stack.grid_columnconfigure(0,weight=1)
        for key,builder in (("home",self._build_home),("preview",self._build_preview),("status",self._build_status),("logs",self._build_logs),("settings",self._build_settings)):
            page=tk.Frame(self.page_stack,bg=BG); page.grid(row=0,column=0,sticky="nsew"); self._pages[key]=page; builder(page)
        self._show_page("home")

    def _build_sidebar(self):
        side=tk.Frame(self,bg=SIDEBAR,width=220,highlightthickness=1,highlightbackground=BORDER); side.grid(row=0,column=0,sticky="ns"); side.grid_propagate(False)
        tk.Label(side,text="STREAMBRIDGE",bg=SIDEBAR,fg=TEXT,font=("Segoe UI",15,"bold")).pack(anchor="e",padx=20,pady=(28,2)); tk.Label(side,text="لوحة بث Windows",bg=SIDEBAR,fg=CYAN,font=("Segoe UI",9,"bold")).pack(anchor="e",padx=20,pady=(0,32))
        tk.Label(side,text="التبويبات",bg=SIDEBAR,fg=MUTED,font=("Segoe UI",8,"bold"),anchor="e").pack(fill="x",padx=20,pady=(0,8))
        items=(("home","dashboard","الرئيسية"),("preview","preview","المعاينة والمؤثرات"),("status","status","حالة الكاميرا"),("logs","logs","السجلات والتشخيص"),("settings","settings","الإعدادات العامة"))
        for key,icon,label in items:
            b=tk.Button(side,text=label,image=self._icons.get(icon),compound="left",anchor="e",command=lambda k=key:self._show_page(k),bg=SIDEBAR,fg=MUTED,activebackground="#192435",activeforeground=TEXT,relief="flat",bd=0,padx=16,pady=12,font=("Segoe UI",10,"bold")); b.pack(fill="x",padx=10,pady=2); self._nav[key]=b
        foot=tk.Frame(side,bg="#101925",highlightthickness=1,highlightbackground=BORDER); foot.pack(side="bottom",fill="x",padx=14,pady=16); tk.Label(foot,text="الإخراج",bg="#101925",fg=MUTED,font=("Segoe UI",8,"bold")).pack(anchor="e",padx=12,pady=(10,3)); tk.Label(foot,text="UnityCapture · DirectShow",bg="#101925",fg=CYAN,font=("Segoe UI",9,"bold")).pack(anchor="e",padx=12,pady=(0,10))

    def _show_page(self,key):
        self._pages[key].tkraise()
        for name,b in self._nav.items(): b.configure(bg="#192435" if name==key else SIDEBAR,fg=CYAN if name==key else MUTED)

    def _card(self,parent,pad=16):
        return tk.Frame(parent,bg=PANEL,highlightthickness=1,highlightbackground=BORDER)

    def _title(self,parent,title,subtitle):
        tk.Label(parent,text=title,bg=BG,fg=TEXT,font=("Segoe UI",22,"bold"),anchor="e").pack(fill="x",pady=(2,3)); tk.Label(parent,text=subtitle,bg=BG,fg=MUTED,font=("Segoe UI",10),anchor="e").pack(fill="x",pady=(0,16))

    def _build_home(self,page):
        self._title(page,"الرئيسية","أدخل رابط TikTok أو رابط بث مباشر ثم استخرج الرابط وشاهد حالة الاتصال.")
        card=self._card(page); card.pack(fill="x",pady=(0,14)); tk.Label(card,text="رابط البث",bg=PANEL,fg=CYAN,font=("Segoe UI",11,"bold"),anchor="e").pack(fill="x",padx=18,pady=(16,5)); tk.Label(card,text="رابط مشاركة TikTok أو رابط M3U8 / RTSP / HTTP مباشر",bg=PANEL,fg=MUTED,font=("Segoe UI",9),anchor="e").pack(fill="x",padx=18,pady=(0,9))
        row=tk.Frame(card,bg=PANEL); row.pack(fill="x",padx=18,pady=(0,12)); row.grid_columnconfigure(0,weight=1); self.url_entry=tk.Entry(row,textvariable=self.url_var,justify="right",bg="#080E19",fg=TEXT,insertbackground=CYAN,relief="flat",font=("Segoe UI",11),highlightthickness=1,highlightbackground="#273449",highlightcolor=CYAN); self.url_entry.grid(row=0,column=0,sticky="ew",ipady=12); tk.Button(row,text="لصق",command=self._paste, bg="#193040",fg=CYAN,relief="flat",bd=0,padx=16,pady=11,font=("Segoe UI",9,"bold")).grid(row=0,column=1,padx=(8,0))
        actions=tk.Frame(card,bg=PANEL); actions.pack(fill="x",padx=18,pady=(0,15)); tk.Button(actions,text="تشغيل المعاينة",command=self._preview_action,bg="#1677FF",fg="white",activebackground="#0B5ED7",relief="flat",bd=0,padx=20,pady=11,font=("Segoe UI",10,"bold")).pack(side="right",padx=(8,0)); tk.Button(actions,text="استخراج الرابط",command=self._extract_only,bg=PINK,fg="white",relief="flat",bd=0,padx=20,pady=11,font=("Segoe UI",10,"bold")).pack(side="right"); self.home_status=tk.Label(actions,text="جاهز · لم يبدأ الاتصال",bg=PANEL,fg=MUTED,font=("Segoe UI",9),anchor="e"); self.home_status.pack(side="right",padx=15)
        info=self._card(page); info.pack(fill="x"); tk.Label(info,text="حالة الاتصال المباشر",bg=PANEL,fg=CYAN,font=("Segoe UI",10,"bold"),anchor="e").pack(fill="x",padx=18,pady=(15,5)); self.home_connection=tk.Label(info,text="لم يتم استخراج أو اختبار الرابط بعد",bg=PANEL,fg=TEXT,font=("Segoe UI",10),anchor="e",justify="right"); self.home_connection.pack(fill="x",padx=18,pady=(0,16))

    def _build_preview(self,page):
        self._title(page,"المعاينة والمؤثرات","صفحة التحكم الوحيدة التي تجمع أدوات Media FX مع معاينة الهاتف.")
        body=tk.Frame(page,bg=BG); body.pack(fill="both",expand=True); body.grid_columnconfigure(0,weight=1); body.grid_columnconfigure(1,weight=0); body.grid_rowconfigure(0,weight=1)
        controls=self._card(body); controls.grid(row=0,column=0,sticky="nsew",padx=(0,18)); controls.grid_columnconfigure(0,weight=1)
        tk.Label(controls,text="التحكم بالمؤثرات",bg=PANEL,fg=CYAN,font=("Segoe UI",12,"bold"),anchor="e").pack(fill="x",padx=18,pady=(16,5)); tk.Label(controls,text="التعديلات لحظية ولا توقف إخراج الكاميرا.",bg=PANEL,fg=MUTED,font=("Segoe UI",9),anchor="e").pack(fill="x",padx=18,pady=(0,8))
        self._fx_group(controls)
        buttonrow=tk.Frame(controls,bg=PANEL); buttonrow.pack(side="bottom",fill="x",padx=18,pady=16); self.start_button=tk.Button(buttonrow,text="بدء البث",command=self._toggle_stream,bg=PINK,fg="white",relief="flat",bd=0,padx=18,pady=10,font=("Segoe UI",9,"bold")); self.start_button.pack(side="right",padx=(5,0)); self.stop_button=tk.Button(buttonrow,text="إيقاف البث",command=self._stop_stream,state="disabled",bg="#334155",fg=TEXT,relief="flat",bd=0,padx=18,pady=10,font=("Segoe UI",9,"bold")); self.stop_button.pack(side="right",padx=(5,0)); self.preview_button=tk.Button(buttonrow,text="إخفاء المعاينة",command=self._toggle_preview,bg="#193040",fg=CYAN,relief="flat",bd=0,padx=14,pady=10,font=("Segoe UI",9,"bold")); self.preview_button.pack(side="right"); self.camera_indicator=tk.Label(buttonrow,text="الكاميرا غير متصلة",image=self._icons.get("status"),compound="right",bg=PANEL,fg=YELLOW,font=("Segoe UI",9,"bold")); self.camera_indicator.pack(side="left")
        phone=self._card(body); phone.grid(row=0,column=1,sticky="ns"); tk.Label(phone,text="المعاينة المباشرة",bg=PANEL,fg=TEXT,font=("Segoe UI",16,"bold"),anchor="e").pack(fill="x",padx=18,pady=(16,2)); tk.Label(phone,text="هاتف 9:16 · ملء الشاشة",bg=PANEL,fg=MUTED,font=("Segoe UI",9),anchor="e").pack(fill="x",padx=18,pady=(0,10)); self.phone_frame=tk.Frame(phone,bg="#02040A",highlightthickness=2,highlightbackground="#26364C",width=378,height=672); self.phone_frame.pack(padx=24,pady=(0,18)); self.phone_frame.pack_propagate(False); self.preview_label=tk.Label(self.phone_frame,text="ستظهر المعاينة هنا بعد بدء البث",bg="#050912",fg=MUTED,font=("Segoe UI",12)); self.preview_label.pack(fill="both",expand=True); self.preview_label.bind("<Configure>",lambda _:self._redraw_latest())

    def _fx_group(self,parent):
        visual=tk.Frame(parent,bg=PANEL); visual.pack(fill="x",padx=12,pady=(0,8)); tk.Checkbutton(visual,text="تفعيل الصورة",variable=self.visual_enabled_var,command=self._schedule_adjustment_apply,bg=PANEL,fg=CYAN,activebackground=PANEL,selectcolor="#080E19",anchor="e").pack(fill="x"); self._slider(visual,"السطوع",self.brightness_var,-12,12,1,lambda v:f"{int(float(v)):+d}%"); self._slider(visual,"التباين",self.contrast_var,90,110,1,lambda v:f"{int(float(v))}%"); self._slider(visual,"درجة اللون",self.hue_var,-10,10,.5,lambda v:f"{float(v):+.1f}°")
        speed=tk.Frame(parent,bg=PANEL); speed.pack(fill="x",padx=12,pady=8); tk.Checkbutton(speed,text="تفعيل السرعة",variable=self.speed_enabled_var,command=self._schedule_adjustment_apply,bg=PANEL,fg=CYAN,activebackground=PANEL,selectcolor="#080E19",anchor="e").pack(fill="x"); self._slider(speed,"السرعة",self.speed_var,.98,1.03,.001,lambda v:f"{float(v):.3f}×")
        audio=tk.Frame(parent,bg=PANEL); audio.pack(fill="x",padx=12,pady=8); tk.Checkbutton(audio,text="تفعيل الصوت",variable=self.audio_enabled_var,command=self._schedule_adjustment_apply,bg=PANEL,fg=CYAN,activebackground=PANEL,selectcolor="#080E19",anchor="e").pack(fill="x"); self._slider(audio,"نبرة الصوت",self.pitch_var,.98,1.03,.001,lambda v:f"{float(v):.3f}×"); self._slider(audio,"مستوى الصوت",self.volume_var,0,100,1,lambda v:f"{int(float(v))}%")

    def _slider(self,parent,label,var,lo,hi,res,fmt):
        row=tk.Frame(parent,bg=PANEL); row.pack(fill="x",pady=2); row.grid_columnconfigure(1,weight=1); tk.Label(row,text=label,bg=PANEL,fg=TEXT,font=("Segoe UI",9),anchor="e",width=15).grid(row=0,column=2,sticky="e"); tk.Scale(row,from_=hi,to=lo,resolution=res,orient="horizontal",variable=var,showvalue=False,command=lambda _:self._schedule_adjustment_apply(),bg=PANEL,fg=TEXT,troughcolor="#202B3D",activebackground=CYAN,highlightthickness=0,sliderlength=18,bd=0).grid(row=0,column=1,sticky="ew",padx=8); lab=tk.Label(row,text=fmt(var.get()),bg=PANEL,fg=CYAN,font=("Consolas",8,"bold"),width=8,anchor="w"); lab.grid(row=0,column=0,sticky="w"); var.trace_add("write",lambda *_:lab.configure(text=fmt(var.get())))

    def _build_status(self,page):
        self._title(page,"حالة الكاميرا","فحص UnityCapture وتفاصيل اتصال الكاميرا الافتراضية.")
        card=self._card(page); card.pack(fill="x",pady=(0,12)); self.status_camera_label=tk.Label(card,text="الكاميرا غير متصلة",bg=PANEL,fg=YELLOW,font=("Segoe UI",14,"bold"),anchor="e"); self.status_camera_label.pack(fill="x",padx=18,pady=(18,8)); self.status_detail=tk.Label(card,text="لم يتم إجراء الفحص بعد",bg=PANEL,fg=MUTED,font=("Segoe UI",10),anchor="e",justify="right"); self.status_detail.pack(fill="x",padx=18,pady=(0,12)); tk.Button(card,text="فحص UnityCapture الآن",command=self._check_camera_setup,bg="#193040",fg=CYAN,relief="flat",bd=0,padx=16,pady=9,font=("Segoe UI",9,"bold")).pack(anchor="e",padx=18,pady=(0,16))
        metrics=self._card(page); metrics.pack(fill="x"); tk.Label(metrics,text="قياسات الجسر",bg=PANEL,fg=CYAN,font=("Segoe UI",10,"bold"),anchor="e").pack(fill="x",padx=18,pady=(15,8)); self.status_metrics=tk.Label(metrics,text="المصدر: انتظار · الإطارات: 0 · 0 FPS",bg=PANEL,fg=TEXT,font=("Segoe UI",10),anchor="e"); self.status_metrics.pack(fill="x",padx=18,pady=(0,16))

    def _build_logs(self,page):
        self._title(page,"السجلات والتشخيص","أخطاء الشبكة وFFmpeg ودورة حياة الكاميرا."); card=self._card(page); card.pack(fill="both",expand=True); self.log_text=tk.Text(card,bg="#080E19",fg="#B9C7D8",relief="flat",wrap="word",font=("Consolas",9),padx=14,pady=12,state="disabled"); self.log_text.pack(fill="both",expand=True,padx=12,pady=12)

    def _build_settings(self,page):
        self._title(page,"الإعدادات العامة","دقة الكاميرا ومعدل الإطارات وتوجيه الصوت إلى VB-CABLE.")
        fmt=self._card(page); fmt.pack(fill="x",pady=(0,12)); tk.Label(fmt,text="إخراج الفيديو",bg=PANEL,fg=CYAN,font=("Segoe UI",10,"bold"),anchor="e").pack(fill="x",padx=18,pady=(15,8)); row=tk.Frame(fmt,bg=PANEL); row.pack(fill="x",padx=18,pady=(0,14)); tk.Label(row,text="الدقة",bg=PANEL,fg=TEXT,font=("Segoe UI",9)).pack(side="right",padx=8); ttk.Combobox(row,textvariable=self.resolution_var,state="readonly",values=["720p · 1280 × 720","1080p · 1920 × 1080"],width=24).pack(side="right"); tk.Label(row,text="الإطارات",bg=PANEL,fg=TEXT,font=("Segoe UI",9)).pack(side="right",padx=18); ttk.Combobox(row,textvariable=self.fps_var,state="readonly",values=["30 FPS","60 FPS"],width=10).pack(side="right")
        cam=self._card(page); cam.pack(fill="x",pady=(0,12)); tk.Label(cam,text="اسم الكاميرا",bg=PANEL,fg=CYAN,font=("Segoe UI",10,"bold"),anchor="e").pack(fill="x",padx=18,pady=(15,7)); ent=tk.Entry(cam,textvariable=self.camera_name_var,justify="right",bg="#080E19",fg=TEXT,insertbackground=CYAN,relief="flat",font=("Segoe UI",10)); ent.pack(fill="x",padx=18,ipady=9); tk.Label(cam,text="الاسم الافتراضي: Unity Video Capture",bg=PANEL,fg=MUTED,font=("Segoe UI",9),anchor="e").pack(fill="x",padx=18,pady=(7,14))
        audio=self._card(page); audio.pack(fill="x"); tk.Label(audio,text="توجيه الصوت",bg=PANEL,fg=CYAN,font=("Segoe UI",10,"bold"),anchor="e").pack(fill="x",padx=18,pady=(15,7)); tk.Label(audio,text="اختر CABLE Input هنا، ثم CABLE Output داخل TikTok LIVE Studio.",bg=PANEL,fg=MUTED,font=("Segoe UI",9),anchor="e").pack(fill="x",padx=18,pady=(0,8)); row=tk.Frame(audio,bg=PANEL); row.pack(fill="x",padx=18,pady=(0,14)); self.audio_combo=ttk.Combobox(row,textvariable=self.audio_device_var,state="readonly"); self.audio_combo.pack(side="right",fill="x",expand=True); tk.Button(row,text="تحديث الأجهزة",command=self._refresh_audio_devices,bg="#193040",fg=CYAN,relief="flat",bd=0,padx=13,pady=8,font=("Segoe UI",9,"bold")).pack(side="right",padx=(8,0))

    def _paste(self):
        try: self.url_entry.delete(0,tk.END); self.url_entry.insert(0,self.clipboard_get().strip()); self._set_status("تم لصق الرابط",CYAN)
        except tk.TclError: self._set_status("الحافظة لا تحتوي على نص",YELLOW)

    def _preview_action(self):
        self._show_page("preview")
        if self._extracted_media_url and self.url_var.get().strip() == self._extracted_input_url:
            self._toggle_stream()
        else:
            self._preview_requested=True
            self._extract_only()

    def _extract_only(self):
        if self._resolving:return
        try: value=normalize_input_url(self.url_var.get())
        except InvalidStreamUrl as exc: messagebox.showerror("رابط غير صالح",str(exc),parent=self); return
        self._resolving=True; self._set_busy(True); self.home_status.configure(text="جارٍ استخراج الرابط…",fg=YELLOW); threading.Thread(target=self._extract_background,args=(value,),daemon=True).start()

    def _extract_background(self,value):
        try: result=resolve_stream_url(value)
        except Exception as exc: self.after(0,lambda:self._extract_error(str(exc))); return
        self.after(0,lambda:self._extract_done(result.media_url,result.source_kind))

    def _extract_error(self,msg): self._resolving=False; self._set_busy(False); self.home_status.configure(text="فشل الاستخراج",fg=RED); self.home_connection.configure(text=msg,fg=RED); self._append_log("خطأ الاستخراج",msg)
    def _extract_done(self,url,kind): self._resolving=False; self._set_busy(False); self._extracted_media_url=url; self.url_var.set(url); self._extracted_input_url=url; self.home_status.configure(text="تم استخراج الرابط",fg=GREEN); self.home_connection.configure(text="رابط M3U8/RTSP جاهز · انتقل إلى المعاينة لتشغيله",fg=GREEN); self._append_log("المصدر","تم استخراج رابط مباشر" if kind!="direct" else "الرابط المباشر جاهز"); self.after(0,self._toggle_stream) if self._preview_requested else None; self._preview_requested=False

    def _get_adjustments(self):
        fps=60 if self.fps_var.get().startswith("60") else 30; width,height=(1920,1080) if self.resolution_var.get().startswith("1080") else (1280,720)
        return {"width":width,"height":height,"fps":fps,"camera_device":self.camera_name_var.get().strip() or DEFAULT_SETTINGS["camera_device"],"visual_enabled":self.visual_enabled_var.get(),"brightness":float(self.brightness_var.get())*2 if self.visual_enabled_var.get() else 0.0,"contrast":float(self.contrast_var.get())/100 if self.visual_enabled_var.get() else 1.0,"hue_shift":float(self.hue_var.get()) if self.visual_enabled_var.get() else 0.0,"speed":float(self.speed_var.get()) if self.speed_enabled_var.get() else 1.0,"audio_enabled":self.audio_enabled_var.get(),"audio_device":self.audio_devices.get(self.audio_device_var.get()),"audio_pitch":float(self.pitch_var.get()) if self.audio_enabled_var.get() else 1.0,"audio_volume":float(self.volume_var.get())/100 if self.audio_enabled_var.get() else .8}

    def _schedule_adjustment_apply(self):
        if self._adjustment_after:
            try:self.after_cancel(self._adjustment_after)
            except tk.TclError:pass
        self._adjustment_after=self.after(250,self._apply_adjustments)
    def _apply_adjustments(self):
        self._adjustment_after=None
        if self.worker and self.worker.is_alive():
            s=self._get_adjustments(); keys=("visual_enabled","brightness","contrast","hue_shift","speed","audio_enabled","audio_device","audio_pitch","audio_volume"); self.worker.update_adjustments(**{k:s[k] for k in keys}); self._set_status("تم تطبيق التأثيرات لحظيًا",CYAN)

    def _toggle_stream(self):
        if self.worker and self.worker.is_alive(): self._stop_stream(); return
        if self._resolving:return
        if not self._extracted_media_url or self.url_var.get().strip() != self._extracted_input_url:
            self._set_status("يجب استخراج رابط M3U8/RTSP أولًا…",YELLOW); self._show_page("home"); self._extract_only(); return
        try:value=normalize_input_url(self.url_var.get())
        except InvalidStreamUrl as exc:messagebox.showerror("رابط غير صالح",str(exc),parent=self);return
        self._resolving=True; self._set_busy(True); self.start_button.configure(state="disabled",text="جارٍ التجهيز…"); self._set_status("جارٍ استخراج الرابط…",YELLOW); threading.Thread(target=self._prepare_stream,args=(value,),daemon=True).start()
    def _prepare_stream(self,value):
        try:
            result=resolve_stream_url(value)
            self.after(0,lambda:self._set_status("تم استخراج الرابط · جارٍ فحص الكاميرا…",YELLOW))
            check=check_unitycapture(self.camera_name_var.get().strip() or DEFAULT_SETTINGS["camera_device"])
            if not check.available:raise RuntimeError(f"الكاميرا الوهمية غير متصلة: {check.message}")
        except Exception as exc:self.after(0,lambda:self._prepare_error(str(exc)));return
        self.after(0,lambda:self._start_resolved(result.media_url))
    def _prepare_error(self,msg):
        self._resolving=False; self._set_busy(False); self.start_button.configure(state="normal",text="بدء البث"); self._set_status("تعذر بدء البث",RED); self._append_log("خطأ",msg); self.camera_indicator.configure(text="الكاميرا غير متصلة",fg=RED); messagebox.showerror("تعذر بدء البث",msg,parent=self)
    def _start_resolved(self,url):
        try:url=validate_stream_url(url)
        except InvalidStreamUrl as exc:self._prepare_error(str(exc));return
        self._resolving=False; self._set_busy(False); s=dict(DEFAULT_SETTINGS); s.update(self._get_adjustments()); self.worker=StreamBridgeEngine(url,settings=s); self.worker.set_preview_enabled(self.preview_var.get()); self._last_error=False; self.start_button.configure(state="disabled",text="البث يعمل"); self.stop_button.configure(state="normal"); self._set_status("جارٍ تشغيل الكاميرا…",YELLOW); self._append_log("المصدر","تم قبول الرابط وبدء البث"); self.worker.start()
    def _stop_stream(self):
        if self.worker and self.worker.is_alive(): self._set_status("جارٍ إيقاف البث…",YELLOW); self.stop_button.configure(state="disabled"); self.worker.request_stop()

    def _check_camera_setup(self): self._set_busy(True); self._set_status("جارٍ فحص UnityCapture…",YELLOW); threading.Thread(target=self._camera_check_bg,daemon=True).start()
    def _camera_check_bg(self):
        result=check_unitycapture(self.camera_name_var.get().strip() or DEFAULT_SETTINGS["camera_device"]); self.after(0,lambda:self._camera_result(result.available,result.message))
    def _camera_result(self,available,msg):
        self._set_busy(False)
        if available:
            for label in (self.camera_indicator,self.status_camera_label):label.configure(text="الكاميرا متصلة",fg=GREEN)
            self.status_detail.configure(text=msg); self._set_status("UnityCapture متصل",GREEN); messagebox.showinfo("UnityCapture",msg,parent=self)
        else:
            self.camera_indicator.configure(text="الكاميرا غير متصلة",fg=RED); self.status_camera_label.configure(text="الكاميرا غير متصلة",fg=RED); self.status_detail.configure(text=msg,fg=RED); self._set_status("الكاميرا غير متصلة",RED)
            if messagebox.askyesno("تثبيت UnityCapture",f"{msg}\n\nفتح التعليمات الرسمية؟",parent=self):webbrowser.open(UNITYCAPTURE_URL)

    def _refresh_audio_devices(self):
        try:devices=list_output_devices()
        except Exception:return
        self.audio_devices={f"{x['index']} · {x['name']}":int(x['index']) for x in devices}; names=list(self.audio_devices); self.audio_combo.configure(values=names); self.audio_device_var.set(next((n for n in names if "cable input" in n.lower()),names[0] if names else ""))
    def _toggle_preview(self):
        self.preview_var.set(not self.preview_var.get()); enabled=self.preview_var.get(); self.preview_button.configure(text="إخفاء المعاينة" if enabled else "تشغيل المعاينة");
        if self.worker and self.worker.is_alive():self.worker.set_preview_enabled(enabled)
        if not enabled:self.preview_label.configure(image="",text="المعاينة مخفية\nإخراج الكاميرا مستمر")

    def _poll_worker(self):
        if self.worker:
            while True:
                try:kind,payload=self.worker.events.get_nowait()
                except queue.Empty:break
                if kind=="status":self._set_status(str(payload),GREEN if "connected" in str(payload).lower() or "ready" in str(payload).lower() else YELLOW); self._append_log("الحالة",str(payload))
                elif kind=="camera":self.camera_indicator.configure(text="الكاميرا متصلة",fg=GREEN); self.status_camera_label.configure(text="الكاميرا متصلة",fg=GREEN); self._append_log("الكاميرا",str(payload))
                elif kind=="metrics":
                    self._last_metrics=payload; text=f"المصدر: {payload.get('signal','انتظار')} · الإطارات: {payload.get('frames',0)} · {payload.get('fps',0):.1f} FPS · {payload.get('resolution','1280×720')}"; self.status_metrics.configure(text=text); self.home_connection.configure(text=text,fg=GREEN if payload.get('signal')=="LIVE" else YELLOW)
                elif kind=="fatal":self._last_error=True; self._set_status(str(payload),RED); self.camera_indicator.configure(text="الكاميرا غير متصلة",fg=RED); self.status_camera_label.configure(text="الكاميرا غير متصلة",fg=RED); self._append_log("خطأ حرج",str(payload))
                elif kind=="finished":self.start_button.configure(state="normal",text="بدء البث"); self.stop_button.configure(state="disabled"); self._set_status("تم إيقاف البث",MUTED)
            if self.preview_var.get():
                newest=None
                while True:
                    try:newest=self.worker.preview_frames.get_nowait()
                    except queue.Empty:break
                if newest is not None:self._show_frame(newest)
        if self._closing and (not self.worker or not self.worker.is_alive()):self.destroy();return
        self.after(40,self._poll_worker)

    def _show_frame(self,bgr):
        if not self.preview_var.get():return
        self._last_display_frame=bgr.copy(); image=Image.fromarray(np.ascontiguousarray(bgr[:,:,::-1]),"RGB"); w,h=image.size; ratio=9/16
        if w/h>ratio:
            cw=int(h*ratio); left=(w-cw)//2; image=image.crop((left,0,left+cw,h))
        else:
            ch=int(w/ratio); top=max(0,(h-ch)//2); image=image.crop((0,top,w,top+ch))
        tw=max(2,self.preview_label.winfo_width()); th=max(2,self.preview_label.winfo_height()); image=ImageOps.fit(image,(tw,th),Image.Resampling.LANCZOS,centering=(.5,.5)); self._photo=ImageTk.PhotoImage(image); self.preview_label.configure(image=self._photo,text="")
    def _redraw_latest(self):
        if self._last_display_frame is not None:self._show_frame(self._last_display_frame)
    def _append_log(self,category,text):
        from datetime import datetime
        line=f"{datetime.now().strftime('%H:%M:%S')}  [{category}]  {text}"; self._log_lines=(self._log_lines+[line])[-500:]; self.log_text.configure(state="normal"); self.log_text.insert(tk.END,line+"\n"); self.log_text.see(tk.END); self.log_text.configure(state="disabled")
    def _set_busy(self,busy):
        if not hasattr(self,"loading"): return
        if busy: self.loading.start(12)
        else: self.loading.stop()

    def _set_status(self,text,color):self.status_chip.configure(text=f"الحالة  {text}",fg=color); self.home_status.configure(text=text,fg=color) if hasattr(self,"home_status") else None
    def _on_close(self):
        if self.worker and self.worker.is_alive():self._closing=True;self.worker.request_stop();self._set_status("جارٍ الإغلاق بأمان…",YELLOW)
        else:self.destroy()
