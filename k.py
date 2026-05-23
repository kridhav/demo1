#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════╗
║  WARRIOR ERP: ULTRA PRO EDITION                                    ║
║  Elite Academic File-Sharing Platform                               ║
║  Flask + MongoDB Atlas + Pillow | Single-File Architecture          ║
╚══════════════════════════════════════════════════════════════════════╝
"""

# ============================================================
# CORE IMPORTS
# ============================================================
from flask import (
    Flask, render_template_string, request, redirect,
    url_for, session, send_file, flash
)
from pymongo import MongoClient
import bson
from bson import ObjectId
from PIL import Image
import io
import os
import mimetypes
import math
from datetime import datetime
from werkzeug.utils import secure_filename

# ============================================================
# FLASK APP INITIALIZATION
# ============================================================
app = Flask(__name__)
app.secret_key = 'warrior-erp-ultra-pro-2024-steel-vault-secret'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max (BSON limit)

# ============================================================
# MONGODB ATLAS CONFIGURATION
# >>> REPLACE WITH YOUR ACTUAL MONGODB ATLAS URI <<<
# ============================================================
MONGO_URI = "mongodb+srv://kridhav59_db_user:3biaODGRL5V2fXQG@cluster0.8sls444.mongodb.net/?appName=warrior"

# Initialize MongoDB client with timeout
client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
db = client['warrior_erp_db']
notes_collection = db['notes']

# ============================================================
# APPLICATION CONSTANTS
# ============================================================
TRACKS = [
    "Class 5",
    "Class 6",
    "Class 9",
    "Class 10",
    "College - Bachelor of Physiotherapy (BPT)",
    "College - General Degree Track"
]

ALLOWED_EXTENSIONS = {
    'pdf', 'jpg', 'jpeg', 'png', 'doc', 'docx',
    'ppt', 'pptx', 'txt', 'xlsx', 'zip'
}

IMAGE_EXTENSIONS = {'jpg', 'jpeg', 'png'}

FACULTY_CREDENTIALS = {
    'teacher': 'teacher123',
    'admin': 'admin123'
}


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def allowed_file(filename):
    """Check if file extension is in the allowed set."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def is_image_file(filename):
    """Determine if a file is an image eligible for compression."""
    ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
    return ext in IMAGE_EXTENSIONS


def format_size(size_bytes):
    """Convert bytes to human-readable format (B, KB, MB, GB)."""
    if size_bytes == 0:
        return "0 B"
    size_names = ["B", "KB", "MB", "GB"]
    i = int(math.floor(math.log(max(size_bytes, 1), 1024)))
    i = min(i, len(size_names) - 1)
    size = size_bytes / (1024 ** i)
    return f"{size:.1f} {size_names[i]}"


def get_mime_type(filename):
    """Return MIME type for a given filename."""
    mime_type, _ = mimetypes.guess_type(filename)
    return mime_type or 'application/octet-stream'


def compress_image(file_data, filename):
    """
    ═══════════════════════════════════════════════════════
    SMART COMPRESSION ENGINE
    ═══════════════════════════════════════════════════════
    Compresses images by 60-80% while preserving text
    legibility. Uses Pillow for in-memory processing.
    - Converts RGBA/PA/P to RGB with white background
    - Resizes if longest dimension > 1400px
    - Saves as JPEG with adaptive quality (25-45)
    """
    try:
        original_size = len(file_data)
        img = Image.open(io.BytesIO(file_data))

        # ── Handle transparency and palette modes ──
        if img.mode in ('RGBA', 'LA', 'PA'):
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'PA':
                img = img.convert('RGBA')
            background.paste(img, mask=img.split()[-1])
            img = background
        elif img.mode == 'P':
            if 'transparency' in img.info:
                img = img.convert('RGBA')
                background = Image.new('RGB', img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[-1])
                img = background
            else:
                img = img.convert('RGB')
        elif img.mode != 'RGB':
            img = img.convert('RGB')

        # ── Smart resize ──
        max_dimension = 1400
        if max(img.size) > max_dimension:
            ratio = max_dimension / max(img.size)
            new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
            img = img.resize(new_size, Image.LANCZOS)

        # ── Adaptive quality based on original size ──
        if original_size > 2 * 1024 * 1024:
            quality = 25
        elif original_size > 1024 * 1024:
            quality = 35
        else:
            quality = 45

        output_buffer = io.BytesIO()
        img.save(output_buffer, format='JPEG', quality=quality, optimize=True)
        compressed_data = output_buffer.getvalue()

        # Safety: if compression didn't help, keep original
        if len(compressed_data) >= original_size:
            return file_data, original_size, original_size, filename

        optimized_size = len(compressed_data)
        new_filename = os.path.splitext(filename)[0] + '.jpg'

        reduction = ((original_size - optimized_size) / original_size) * 100
        print(f"  ✅ Compressed: {filename} | "
              f"{format_size(original_size)} → {format_size(optimized_size)} | "
              f"{reduction:.1f}% saved")

        return compressed_data, original_size, optimized_size, new_filename

    except Exception as e:
        print(f"  ⚠️ Compression error for {filename}: {e}")
        return file_data, len(file_data), len(file_data), filename


def prepare_notes_for_template(notes_cursor):
    """Convert MongoDB cursor to template-ready list of dicts."""
    notes = []
    for note in notes_cursor:
        note['_id'] = str(note['_id'])
        note['original_size_fmt'] = format_size(note.get('original_size', 0))
        note['optimized_size_fmt'] = format_size(note.get('optimized_size', 0))
        saved = note.get('original_size', 0) - note.get('optimized_size', 0)
        note['space_saved_fmt'] = format_size(saved)
        pct = 0
        if note.get('original_size', 0) > 0:
            pct = (saved / note['original_size']) * 100
        note['space_saved_pct'] = f"{pct:.1f}"
        notes.append(note)
    return notes


# Register Jinja2 filter for size formatting
app.jinja_env.filters['format_size'] = format_size


# ============================================================
# SHARED TEMPLATE FRAGMENTS
# ============================================================

COMMON_HEAD = """
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Warrior ERP: Ultra Pro Edition</title>
<script src="https://cdn.tailwindcss.com"></script>
<script>
tailwind.config = {
  theme: {
    extend: {
      colors: {
        'cyber': { 950:'#020617', 900:'#0f172a', 800:'#1e293b', 700:'#334155' }
      },
      animation: {
        'glow-pulse':'glowPulse 2s ease-in-out infinite',
        'fade-in':'fadeIn 0.6s ease-out forwards',
        'slide-up':'slideUp 0.5s ease-out forwards',
        'float':'float 6s ease-in-out infinite',
      }
    }
  }
}
</script>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&family=Orbitron:wght@400;500;600;700;800;900&display=swap');
  *{font-family:'Inter',sans-serif}
  .font-orbitron{font-family:'Orbitron',sans-serif}
  ::-webkit-scrollbar{width:8px}
  ::-webkit-scrollbar-track{background:#0f172a}
  ::-webkit-scrollbar-thumb{background:linear-gradient(180deg,#f59e0b,#f97316);border-radius:4px}
  ::-webkit-scrollbar-thumb:hover{background:linear-gradient(180deg,#fbbf24,#fb923c)}
  @keyframes glowPulse{
    0%,100%{box-shadow:0 0 20px rgba(245,158,11,.3),0 0 40px rgba(245,158,11,.1)}
    50%{box-shadow:0 0 30px rgba(245,158,11,.5),0 0 60px rgba(245,158,11,.2)}
  }
  @keyframes fadeIn{from{opacity:0}to{opacity:1}}
  @keyframes slideUp{from{opacity:0;transform:translateY(30px)}to{opacity:1;transform:translateY(0)}}
  @keyframes float{0%,100%{transform:translateY(0)}50%{transform:translateY(-10px)}}
  .glass-card{
    background:rgba(30,41,59,.5);backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px);
    border:1px solid rgba(245,158,11,.15);border-radius:16px;transition:all .3s ease;
  }
  .glass-card:hover{
    border-color:rgba(245,158,11,.4);
    box-shadow:0 0 25px rgba(245,158,11,.15),0 8px 32px rgba(0,0,0,.3);
    transform:translateY(-2px);
  }
  .neon-border{border:1px solid rgba(245,158,11,.4);box-shadow:0 0 15px rgba(245,158,11,.2),inset 0 0 15px rgba(245,158,11,.05)}
  .gradient-text{background:linear-gradient(135deg,#fbbf24,#f59e0b,#f97316);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}
  .cyber-grid{
    background-image:linear-gradient(rgba(245,158,11,.03) 1px,transparent 1px),linear-gradient(90deg,rgba(245,158,11,.03) 1px,transparent 1px);
    background-size:60px 60px;
  }
  .btn-glow{background:linear-gradient(135deg,#f59e0b,#f97316);box-shadow:0 0 20px rgba(245,158,11,.3);transition:all .3s ease}
  .btn-glow:hover{box-shadow:0 0 30px rgba(245,158,11,.5),0 0 60px rgba(245,158,11,.2);transform:translateY(-1px)}
  .input-cyber:focus{border-color:#f59e0b!important;box-shadow:0 0 15px rgba(245,158,11,.2);outline:none}
  .stagger-1{animation-delay:.1s}.stagger-2{animation-delay:.2s}.stagger-3{animation-delay:.3s}
  .stagger-4{animation-delay:.4s}.stagger-5{animation-delay:.5s}.stagger-6{animation-delay:.6s}
  .note-card{opacity:0;animation:slideUp .5s ease-out forwards}
  .flash-msg{animation:fadeIn .3s ease-out}
  .cyber-table th{background:rgba(245,158,11,.1);border-bottom:2px solid rgba(245,158,11,.3)}
  .cyber-table td{border-bottom:1px solid rgba(51,65,85,.5)}
  .cyber-table tr:hover td{background:rgba(245,158,11,.05)}
</style>
"""

NAV_BAR = """
<nav class="relative z-50 px-6 py-4 flex items-center justify-between border-b border-slate-800/50 bg-cyber-950/80 backdrop-blur-md">
  <a href="/" class="flex items-center gap-3 group">
    <div class="w-9 h-9 rounded-lg bg-gradient-to-br from-amber-500 to-orange-600 flex items-center justify-center group-hover:scale-110 transition-transform">
      <svg class="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"/></svg>
    </div>
    <span class="font-orbitron text-lg font-bold gradient-text">WARRIOR ERP</span>
  </a>
  <div class="flex items-center gap-4">
    {nav_right}
  </div>
</nav>
"""


# ============================================================
# LANDING PAGE TEMPLATE
# ============================================================
LANDING_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>""" + COMMON_HEAD + """</head>
<body class="min-h-screen bg-cyber-950 text-white cyber-grid overflow-x-hidden">

  <!-- Animated background orbs -->
  <div class="fixed inset-0 pointer-events-none overflow-hidden">
    <div class="absolute top-1/4 left-1/4 w-96 h-96 bg-amber-500/5 rounded-full blur-3xl animate-float"></div>
    <div class="absolute bottom-1/4 right-1/4 w-80 h-80 bg-orange-500/5 rounded-full blur-3xl animate-float" style="animation-delay:3s"></div>
    <div class="absolute top-3/4 left-3/4 w-64 h-64 bg-amber-600/5 rounded-full blur-3xl animate-float" style="animation-delay:1.5s"></div>
  </div>

  <div class="relative z-10 min-h-screen flex flex-col">

    <!-- Header -->
    <header class="py-10 text-center animate-fade-in">
      <div class="inline-flex items-center gap-3 mb-4">
        <div class="w-14 h-14 rounded-xl bg-gradient-to-br from-amber-500 to-orange-600 flex items-center justify-center animate-glow-pulse">
          <svg class="w-8 h-8 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"/></svg>
        </div>
        <h1 class="font-orbitron text-3xl md:text-5xl font-bold gradient-text">WARRIOR ERP</h1>
      </div>
      <p class="text-slate-400 text-lg tracking-[0.3em] uppercase font-light">Ultra Pro Edition</p>
      <div class="mt-3 h-px w-56 mx-auto bg-gradient-to-r from-transparent via-amber-500/50 to-transparent"></div>
      <p class="mt-4 text-slate-500 text-sm max-w-md mx-auto">Elite Academic File-Sharing Platform — Compressed. Secured. Delivered.</p>
    </header>

    <!-- Gateway Cards -->
    <main class="flex-1 flex items-center justify-center px-4 pb-16">
      <div class="grid md:grid-cols-2 gap-8 max-w-4xl w-full">

        <!-- Student Access Hub -->
        <a href="/student" class="group glass-card p-8 md:p-10 text-center animate-slide-up stagger-1 block no-underline">
          <div class="w-20 h-20 mx-auto mb-6 rounded-2xl bg-gradient-to-br from-blue-500 to-cyan-400 flex items-center justify-center group-hover:scale-110 transition-transform duration-300 shadow-lg shadow-blue-500/20">
            <svg class="w-10 h-10 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253"/></svg>
          </div>
          <h2 class="font-orbitron text-2xl font-bold text-white mb-3">Student Access Hub</h2>
          <p class="text-slate-400 mb-6 leading-relaxed">Browse and download academic notes for your track. No login required — instant access to knowledge.</p>
          <div class="inline-flex items-center gap-2 text-cyan-400 font-semibold group-hover:gap-3 transition-all">
            <span>Enter Hub</span>
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 7l5 5m0 0l-5 5m5-5H6"/></svg>
          </div>
        </a>

        <!-- Faculty Control Terminal -->
        <a href="/faculty/login" class="group glass-card p-8 md:p-10 text-center animate-slide-up stagger-2 block no-underline">
          <div class="w-20 h-20 mx-auto mb-6 rounded-2xl bg-gradient-to-br from-amber-500 to-orange-600 flex items-center justify-center group-hover:scale-110 transition-transform duration-300 animate-glow-pulse shadow-lg shadow-amber-500/20">
            <svg class="w-10 h-10 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"/></svg>
          </div>
          <h2 class="font-orbitron text-2xl font-bold text-white mb-3">Faculty Control Terminal</h2>
          <p class="text-slate-400 mb-6 leading-relaxed">Secure portal for teachers and admins. Upload, manage, and analyze academic resources.</p>
          <div class="inline-flex items-center gap-2 text-amber-400 font-semibold group-hover:gap-3 transition-all">
            <span>Access Terminal</span>
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"/></svg>
          </div>
        </a>

      </div>
    </main>

    <!-- Footer -->
    <footer class="py-6 text-center text-slate-600 text-sm border-t border-slate-800/30">
      <p>Warrior ERP: Ultra Pro Edition &copy; 2024 — Empowering Academic Excellence</p>
    </footer>
  </div>
</body>
</html>"""


# ============================================================
# STUDENT TRACK SELECTION TEMPLATE
# ============================================================
STUDENT_SELECT_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>""" + COMMON_HEAD + """</head>
<body class="min-h-screen bg-cyber-950 text-white cyber-grid">

  <div class="fixed inset-0 pointer-events-none overflow-hidden">
    <div class="absolute top-1/3 right-1/4 w-80 h-80 bg-cyan-500/5 rounded-full blur-3xl animate-float"></div>
    <div class="absolute bottom-1/3 left-1/4 w-64 h-64 bg-blue-500/5 rounded-full blur-3xl animate-float" style="animation-delay:2s"></div>
  </div>

  <div class="relative z-10 min-h-screen flex flex-col">
    """ + NAV_BAR.format(nav_right='<span class="text-slate-500 text-sm">Student Portal</span>') + """

    <main class="flex-1 flex items-center justify-center px-4 py-12">
      <div class="glass-card p-8 md:p-12 max-w-lg w-full animate-slide-up">
        <div class="text-center mb-8">
          <div class="w-16 h-16 mx-auto mb-4 rounded-2xl bg-gradient-to-br from-blue-500 to-cyan-400 flex items-center justify-center">
            <svg class="w-8 h-8 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253"/></svg>
          </div>
          <h2 class="font-orbitron text-2xl font-bold gradient-text mb-2">Select Your Track</h2>
          <p class="text-slate-400 text-sm">Choose your academic track to access curated notes</p>
        </div>

        <form method="POST" action="/student">
          <div class="mb-6">
            <label class="block text-slate-300 text-sm font-medium mb-2">Academic Track</label>
            <select name="track" required class="w-full bg-cyber-800/80 border border-slate-700 rounded-xl px-4 py-3 text-white input-cyber transition-all appearance-none cursor-pointer" style="background-image:url('data:image/svg+xml;utf8,<svg fill=\\'%23f59e0b\\' viewBox=\\'0 0 20 20\\' xmlns=\\'http://www.w3.org/2000/svg\\'><path fill-rule=\\'evenodd\\' d=\\'M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z\\' clip-rule=\\'evenodd\\'/></svg>');background-repeat:no-repeat;background-position:right 12px center;background-size:20px">
              <option value="" disabled selected class="text-slate-500">— Choose your track —</option>
              {% for track in tracks %}
              <option value="{{ track }}" class="bg-slate-800">{{ track }}</option>
              {% endfor %}
            </select>
          </div>
          <button type="submit" class="w-full btn-glow text-white font-bold py-3 px-6 rounded-xl font-orbitron tracking-wider">
            ACCESS DASHBOARD
          </button>
        </form>
      </div>
    </main>
  </div>
</body>
</html>"""


# ============================================================
# STUDENT DASHBOARD TEMPLATE
# ============================================================
STUDENT_DASHBOARD_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>""" + COMMON_HEAD + """</head>
<body class="min-h-screen bg-cyber-950 text-white cyber-grid">

  <div class="fixed inset-0 pointer-events-none overflow-hidden">
    <div class="absolute top-1/3 left-1/5 w-72 h-72 bg-cyan-500/5 rounded-full blur-3xl animate-float"></div>
    <div class="absolute bottom-1/4 right-1/5 w-80 h-80 bg-blue-500/5 rounded-full blur-3xl animate-float" style="animation-delay:2.5s"></div>
  </div>

  <div class="relative z-10 min-h-screen flex flex-col">
    """ + NAV_BAR.format(nav_right='<a href="/student" class="text-slate-400 hover:text-amber-400 text-sm transition-colors flex items-center gap-1"><svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7"/></svg>Change Track</a>') + """

    <main class="flex-1 px-4 md:px-8 py-8 max-w-7xl mx-auto w-full">

      <!-- Track Header -->
      <div class="mb-8 animate-fade-in">
        <div class="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div>
            <p class="text-amber-400 text-sm font-medium tracking-widest uppercase mb-1">Student Dashboard</p>
            <h1 class="font-orbitron text-2xl md:text-3xl font-bold text-white">{{ track }}</h1>
          </div>
          <div class="flex items-center gap-3">
            <span class="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-cyan-500/10 border border-cyan-500/20 text-cyan-400 text-sm">
              <span class="w-2 h-2 rounded-full bg-cyan-400 animate-pulse"></span>
              {{ notes|length }} Note{{ 's' if notes|length != 1 else '' }} Available
            </span>
          </div>
        </div>
      </div>

      <!-- Search Bar -->
      <div class="mb-8 animate-slide-up stagger-1">
        <div class="relative max-w-xl">
          <svg class="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"/></svg>
          <input id="searchInput" type="text" placeholder="Search by title or subject..." class="w-full bg-cyber-800/60 border border-slate-700 rounded-xl pl-12 pr-4 py-3 text-white placeholder-slate-500 input-cyber transition-all">
        </div>
      </div>

      <!-- Notes Grid -->
      {% if notes %}
      <div id="notesGrid" class="grid sm:grid-cols-2 lg:grid-cols-3 gap-6">
        {% for note in notes %}
        <div class="note-card glass-card p-6 flex flex-col" style="animation-delay:{{ loop.index0 * 0.08 }}s" data-title="{{ note.title|lower }}" data-subject="{{ note.subject|lower }}">
          <!-- File type badge -->
          <div class="flex items-center justify-between mb-4">
            <span class="px-3 py-1 rounded-lg text-xs font-bold uppercase tracking-wider
              {% if note.filename|lower|regex_search('\\\\.pdf$') %}bg-red-500/20 text-red-400
              {% elif note.filename|lower|regex_search('\\\\.(jpg|jpeg|png)$') %}bg-green-500/20 text-green-400
              {% elif note.filename|lower|regex_search('\\\\.(doc|docx)$') %}bg-blue-500/20 text-blue-400
              {% elif note.filename|lower|regex_search('\\\\.(ppt|pptx)$') %}bg-orange-500/20 text-orange-400
              {% else %}bg-slate-500/20 text-slate-400{% endif %}">
              {{ note.filename.rsplit('.', 1)[-1]|upper if '.' in note.filename else 'FILE' }}
            </span>
            <span class="text-slate-500 text-xs">{{ note.optimized_size_fmt }}</span>
          </div>

          <!-- Note details -->
          <h3 class="text-white font-semibold text-lg mb-1 line-clamp-2">{{ note.title }}</h3>
          <p class="text-amber-400/80 text-sm mb-3">{{ note.subject }}</p>
          <p class="text-slate-500 text-xs mb-4">by {{ note.uploaded_by }}</p>

          <!-- Spacer -->
          <div class="flex-1"></div>

          <!-- Download button -->
          <a href="/download/{{ note._id }}" class="w-full inline-flex items-center justify-center gap-2 bg-cyber-800/80 hover:bg-amber-500/20 border border-slate-700 hover:border-amber-500/40 rounded-xl py-2.5 text-sm font-medium text-slate-300 hover:text-amber-400 transition-all">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/></svg>
            Download
          </a>
        </div>
        {% endfor %}
      </div>
      {% else %}
      <!-- Empty state -->
      <div class="text-center py-20 animate-fade-in">
        <div class="w-24 h-24 mx-auto mb-6 rounded-2xl bg-slate-800/50 flex items-center justify-center">
          <svg class="w-12 h-12 text-slate-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg>
        </div>
        <h3 class="font-orbitron text-xl font-bold text-slate-400 mb-2">No Notes Yet</h3>
        <p class="text-slate-500 max-w-sm mx-auto">Notes for this track haven't been uploaded yet. Check back soon!</p>
      </div>
      {% endif %}

    </main>
  </div>

  <!-- Live Search Script -->
  <script>
    document.getElementById('searchInput').addEventListener('input', function(e) {
      const query = e.target.value.toLowerCase().trim();
      const cards = document.querySelectorAll('.note-card');
      let visible = 0;
      cards.forEach(function(card) {
        const title = card.dataset.title || '';
        const subject = card.dataset.subject || '';
        const match = title.includes(query) || subject.includes(query);
        card.style.display = match ? '' : 'none';
        if (match) visible++;
      });
      // Update count display if needed
    });
  </script>
</body>
</html>"""


# ============================================================
# FACULTY LOGIN TEMPLATE
# ============================================================
FACULTY_LOGIN_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>""" + COMMON_HEAD + """</head>
<body class="min-h-screen bg-cyber-950 text-white cyber-grid">

  <div class="fixed inset-0 pointer-events-none overflow-hidden">
    <div class="absolute top-1/3 right-1/3 w-96 h-96 bg-amber-500/5 rounded-full blur-3xl animate-float"></div>
    <div class="absolute bottom-1/4 left-1/3 w-72 h-72 bg-orange-500/5 rounded-full blur-3xl animate-float" style="animation-delay:2s"></div>
  </div>

  <div class="relative z-10 min-h-screen flex flex-col">
    """ + NAV_BAR.format(nav_right='<a href="/" class="text-slate-400 hover:text-amber-400 text-sm transition-colors flex items-center gap-1"><svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7"/></svg>Back</a>') + """

    <main class="flex-1 flex items-center justify-center px-4 py-12">
      <div class="glass-card neon-border p-8 md:p-10 max-w-md w-full animate-slide-up">

        <!-- Lock Icon -->
        <div class="text-center mb-8">
          <div class="w-16 h-16 mx-auto mb-4 rounded-2xl bg-gradient-to-br from-amber-500 to-orange-600 flex items-center justify-center animate-glow-pulse">
            <svg class="w-8 h-8 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"/></svg>
          </div>
          <h2 class="font-orbitron text-2xl font-bold gradient-text mb-1">Secure Login</h2>
          <p class="text-slate-400 text-sm">Faculty Control Terminal — Authorized Only</p>
        </div>

        <!-- Flash Messages -->
        {% with messages = get_flashed_messages(with_categories=true) %}
        {% if messages %}
        {% for category, message in messages %}
        <div class="flash-msg mb-4 px-4 py-3 rounded-xl text-sm font-medium border
          {% if category == 'error' %}bg-red-500/10 border-red-500/30 text-red-400
          {% elif category == 'success' %}bg-green-500/10 border-green-500/30 text-green-400
          {% else %}bg-amber-500/10 border-amber-500/30 text-amber-400{% endif %}">
          {{ message }}
        </div>
        {% endfor %}
        {% endif %}
        {% endwith %}

        <!-- Login Form -->
        <form method="POST" action="/faculty/login">
          <div class="mb-5">
            <label class="block text-slate-300 text-sm font-medium mb-2">Username</label>
            <input type="text" name="username" required autocomplete="off"
              class="w-full bg-cyber-800/80 border border-slate-700 rounded-xl px-4 py-3 text-white placeholder-slate-500 input-cyber transition-all"
              placeholder="Enter username">
          </div>
          <div class="mb-6">
            <label class="block text-slate-300 text-sm font-medium mb-2">Password</label>
            <input type="password" name="password" required
              class="w-full bg-cyber-800/80 border border-slate-700 rounded-xl px-4 py-3 text-white placeholder-slate-500 input-cyber transition-all"
              placeholder="Enter password">
          </div>
          <button type="submit" class="w-full btn-glow text-white font-bold py-3 px-6 rounded-xl font-orbitron tracking-wider text-sm">
            AUTHENTICATE
          </button>
        </form>

        <div class="mt-6 pt-5 border-t border-slate-700/50 text-center">
          <p class="text-slate-500 text-xs">🔒 End-to-end secured faculty access</p>
        </div>
      </div>
    </main>
  </div>
</body>
</html>"""


# ============================================================
# FACULTY DASHBOARD TEMPLATE
# ============================================================
FACULTY_DASHBOARD_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>""" + COMMON_HEAD + """</head>
<body class="min-h-screen bg-cyber-950 text-white cyber-grid">

  <div class="fixed inset-0 pointer-events-none overflow-hidden">
    <div class="absolute top-1/4 right-1/4 w-96 h-96 bg-amber-500/5 rounded-full blur-3xl animate-float"></div>
    <div class="absolute bottom-1/3 left-1/4 w-72 h-72 bg-orange-500/5 rounded-full blur-3xl animate-float" style="animation-delay:2s"></div>
  </div>

  <div class="relative z-10 min-h-screen flex flex-col">
    """ + NAV_BAR.format(nav_right="""
      <span class="text-slate-400 text-sm hidden sm:inline">Logged in as <strong class="text-amber-400">{{ user }}</strong> {{ '(Admin)' if user == 'admin' else '(Teacher)' }}</span>
      <a href="/faculty/logout" class="px-4 py-2 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-sm hover:bg-red-500/20 transition-all">Logout</a>
    """) + """

    <main class="flex-1 px-4 md:px-8 py-8 max-w-7xl mx-auto w-full">

      <!-- Flash Messages -->
      {% with messages = get_flashed_messages(with_categories=true) %}
      {% if messages %}
      {% for category, message in messages %}
      <div class="flash-msg mb-6 px-5 py-3 rounded-xl text-sm font-medium border
        {% if category == 'error' %}bg-red-500/10 border-red-500/30 text-red-400
        {% elif category == 'success' %}bg-green-500/10 border-green-500/30 text-green-400
        {% else %}bg-amber-500/10 border-amber-500/30 text-amber-400{% endif %}">
        {{ message }}
      </div>
      {% endfor %}
      {% endif %}
      {% endwith %}

      <!-- Dashboard Header -->
      <div class="mb-8 animate-fade-in">
        <p class="text-amber-400 text-sm font-medium tracking-widest uppercase mb-1">Faculty Control Terminal</p>
        <h1 class="font-orbitron text-2xl md:text-3xl font-bold text-white">Dashboard</h1>
      </div>

      <!-- Stats Row -->
      <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
        <div class="glass-card p-5 text-center animate-slide-up stagger-1">
          <p class="text-3xl font-bold gradient-text font-orbitron">{{ total_notes }}</p>
          <p class="text-slate-400 text-xs mt-1 uppercase tracking-wider">Total Notes</p>
        </div>
        <div class="glass-card p-5 text-center animate-slide-up stagger-2">
          <p class="text-3xl font-bold text-cyan-400 font-orbitron">{{ total_original_fmt }}</p>
          <p class="text-slate-400 text-xs mt-1 uppercase tracking-wider">Original Size</p>
        </div>
        <div class="glass-card p-5 text-center animate-slide-up stagger-3">
          <p class="text-3xl font-bold text-green-400 font-orbitron">{{ total_optimized_fmt }}</p>
          <p class="text-slate-400 text-xs mt-1 uppercase tracking-wider">Optimized Size</p>
        </div>
        <div class="glass-card p-5 text-center animate-slide-up stagger-4">
          <p class="text-3xl font-bold text-amber-400 font-orbitron">{{ total_saved_pct }}%</p>
          <p class="text-slate-400 text-xs mt-1 uppercase tracking-wider">Space Saved</p>
        </div>
      </div>

      <div class="grid lg:grid-cols-5 gap-8">

        <!-- Upload Form (2 cols) -->
        <div class="lg:col-span-2 animate-slide-up stagger-2">
          <div class="glass-card p-6 md:p-8 sticky top-8">
            <h2 class="font-orbitron text-lg font-bold text-white mb-6 flex items-center gap-2">
              <svg class="w-5 h-5 text-amber-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"/></svg>
              Upload Note
            </h2>
            <form method="POST" action="/faculty/upload" enctype="multipart/form-data" id="uploadForm">
              <div class="mb-4">
                <label class="block text-slate-300 text-sm font-medium mb-2">Title</label>
                <input type="text" name="title" required
                  class="w-full bg-cyber-800/80 border border-slate-700 rounded-xl px-4 py-2.5 text-white placeholder-slate-500 input-cyber transition-all text-sm"
                  placeholder="e.g., Chapter 5 - Newton's Laws">
              </div>
              <div class="mb-4">
                <label class="block text-slate-300 text-sm font-medium mb-2">Category / Track</label>
                <select name="category" required class="w-full bg-cyber-800/80 border border-slate-700 rounded-xl px-4 py-2.5 text-white input-cyber transition-all text-sm appearance-none cursor-pointer" style="background-image:url('data:image/svg+xml;utf8,<svg fill=\\'%23f59e0b\\' viewBox=\\'0 0 20 20\\' xmlns=\\'http://www.w3.org/2000/svg\\'><path fill-rule=\\'evenodd\\' d=\\'M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z\\' clip-rule=\\'evenodd\\'/></svg>');background-repeat:no-repeat;background-position:right 12px center;background-size:20px">
                  <option value="" disabled selected class="text-slate-500">— Select track —</option>
                  {% for track in tracks %}
                  <option value="{{ track }}" class="bg-slate-800">{{ track }}</option>
                  {% endfor %}
                </select>
              </div>
              <div class="mb-4">
                <label class="block text-slate-300 text-sm font-medium mb-2">Subject</label>
                <input type="text" name="subject" required
                  class="w-full bg-cyber-800/80 border border-slate-700 rounded-xl px-4 py-2.5 text-white placeholder-slate-500 input-cyber transition-all text-sm"
                  placeholder="e.g., Physics, Mathematics">
              </div>
              <div class="mb-6">
                <label class="block text-slate-300 text-sm font-medium mb-2">File Attachment</label>
                <div id="dropZone" class="relative border-2 border-dashed border-slate-700 hover:border-amber-500/40 rounded-xl p-6 text-center transition-all cursor-pointer bg-cyber-800/30">
                  <input type="file" name="file" required id="fileInput" class="absolute inset-0 w-full h-full opacity-0 cursor-pointer">
                  <svg class="w-8 h-8 mx-auto text-slate-500 mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"/></svg>
                  <p id="fileLabel" class="text-slate-400 text-sm">Click or drag file here</p>
                  <p class="text-slate-600 text-xs mt-1">PDF, JPG, PNG, DOC, PPT, TXT up to 16MB</p>
                </div>
              </div>
              <button type="submit" id="uploadBtn" class="w-full btn-glow text-white font-bold py-3 px-6 rounded-xl font-orbitron tracking-wider text-sm">
                UPLOAD & COMPRESS
              </button>
            </form>
          </div>
        </div>

        <!-- Analytics Table (3 cols) -->
        <div class="lg:col-span-3 animate-slide-up stagger-3">
          <div class="glass-card p-6 md:p-8">
            <h2 class="font-orbitron text-lg font-bold text-white mb-6 flex items-center gap-2">
              <svg class="w-5 h-5 text-amber-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"/></svg>
              Analytics & Management
            </h2>

            {% if notes %}
            <div class="overflow-x-auto -mx-6 md:-mx-8">
              <table class="w-full cyber-table text-sm min-w-[700px]">
                <thead>
                  <tr>
                    <th class="px-4 py-3 text-left text-amber-400 font-semibold text-xs uppercase tracking-wider">Title</th>
                    <th class="px-4 py-3 text-left text-amber-400 font-semibold text-xs uppercase tracking-wider">Track</th>
                    <th class="px-4 py-3 text-left text-amber-400 font-semibold text-xs uppercase tracking-wider">Subject</th>
                    <th class="px-4 py-3 text-left text-amber-400 font-semibold text-xs uppercase tracking-wider">Original</th>
                    <th class="px-4 py-3 text-left text-amber-400 font-semibold text-xs uppercase tracking-wider">Optimized</th>
                    <th class="px-4 py-3 text-left text-amber-400 font-semibold text-xs uppercase tracking-wider">Saved</th>
                    <th class="px-4 py-3 text-left text-amber-400 font-semibold text-xs uppercase tracking-wider">By</th>
                    <th class="px-4 py-3 text-center text-amber-400 font-semibold text-xs uppercase tracking-wider">Action</th>
                  </tr>
                </thead>
                <tbody>
                  {% for note in notes %}
                  <tr class="transition-colors">
                    <td class="px-4 py-3">
                      <div class="font-medium text-white truncate max-w-[140px]" title="{{ note.title }}">{{ note.title }}</div>
                      <div class="text-slate-500 text-xs truncate max-w-[140px]">{{ note.filename }}</div>
                    </td>
                    <td class="px-4 py-3 text-slate-300 text-xs">{{ note.category }}</td>
                    <td class="px-4 py-3 text-slate-300">{{ note.subject }}</td>
                    <td class="px-4 py-3 text-cyan-400 font-mono text-xs">{{ note.original_size_fmt }}</td>
                    <td class="px-4 py-3 text-green-400 font-mono text-xs">{{ note.optimized_size_fmt }}</td>
                    <td class="px-4 py-3">
                      <span class="inline-flex items-center px-2 py-0.5 rounded-md text-xs font-bold bg-amber-500/15 text-amber-400">
                        {{ note.space_saved_pct }}%
                      </span>
                    </td>
                    <td class="px-4 py-3 text-slate-400 text-xs">{{ note.uploaded_by }}</td>
                    <td class="px-4 py-3 text-center">
                      {% if user == 'admin' or note.uploaded_by == user %}
                      <form method="POST" action="/faculty/delete/{{ note._id }}" onsubmit="return confirm('Delete this note permanently?');" class="inline">
                        <button type="submit" class="px-3 py-1.5 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-xs hover:bg-red-500/25 transition-all font-medium">
                          Delete
                        </button>
                      </form>
                      {% else %}
                      <span class="text-slate-600 text-xs" title="Only admin or the uploader can delete">🔒</span>
                      {% endif %}
                    </td>
                  </tr>
                  {% endfor %}
                </tbody>
              </table>
            </div>
            {% else %}
            <div class="text-center py-12">
              <svg class="w-12 h-12 mx-auto text-slate-600 mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4"/></svg>
              <p class="text-slate-400 font-medium">No notes uploaded yet</p>
              <p class="text-slate-500 text-sm mt-1">Use the upload form to add your first note</p>
            </div>
            {% endif %}
          </div>
        </div>

      </div>
    </main>
  </div>

  <!-- Upload form scripts -->
  <script>
    // File input label updater
    document.getElementById('fileInput').addEventListener('change', function(e) {
      const label = document.getElementById('fileLabel');
      if (e.target.files.length > 0) {
        const file = e.target.files[0];
        const sizeMB = (file.size / (1024 * 1024)).toFixed(2);
        label.textContent = file.name + ' (' + sizeMB + ' MB)';
        label.classList.remove('text-slate-400');
        label.classList.add('text-amber-400');
      } else {
        label.textContent = 'Click or drag file here';
        label.classList.remove('text-amber-400');
        label.classList.add('text-slate-400');
      }
    });

    // Drop zone visual feedback
    const dropZone = document.getElementById('dropZone');
    const fileInput = document.getElementById('fileInput');
    ['dragenter','dragover'].forEach(ev => {
      dropZone.addEventListener(ev, function(e) {
        e.preventDefault();
        dropZone.classList.add('border-amber-500/60', 'bg-amber-500/5');
      });
    });
    ['dragleave','drop'].forEach(ev => {
      dropZone.addEventListener(ev, function(e) {
        e.preventDefault();
        dropZone.classList.remove('border-amber-500/60', 'bg-amber-500/5');
      });
    });
    dropZone.addEventListener('drop', function(e) {
      const files = e.dataTransfer.files;
      if (files.length > 0) {
        fileInput.files = files;
        fileInput.dispatchEvent(new Event('change'));
      }
    });

    // Upload button loading state
    document.getElementById('uploadForm').addEventListener('submit', function() {
      const btn = document.getElementById('uploadBtn');
      btn.textContent = 'PROCESSING...';
      btn.disabled = true;
      btn.classList.add('opacity-60');
    });
  </script>
</body>
</html>"""


# ============================================================
# ROUTES
# ============================================================

@app.route('/')
def index():
    """Gatekeeper Landing Page — entry point for all users."""
    return render_template_string(LANDING_TEMPLATE)


@app.route('/student', methods=['GET', 'POST'])
def student_select():
    """
    Student Track Selection.
    GET: Shows the track dropdown form.
    POST: Processes the selection and redirects to dashboard.
    """
    if request.method == 'POST':
        track = request.form.get('track', '').strip()
        if track and track in TRACKS:
            return redirect(url_for('student_dashboard', track=track))
        flash("Please select a valid track.", "error")
        return redirect(url_for('student_select'))

    return render_template_string(STUDENT_SELECT_TEMPLATE, tracks=TRACKS)


@app.route('/student/dashboard')
def student_dashboard():
    """
    Student Dashboard — displays notes for the selected track.
    No login required. Includes live JS search.
    """
    track = request.args.get('track', '').strip()
    if not track or track not in TRACKS:
        flash("Please select a valid track.", "error")
        return redirect(url_for('student_select'))

    # Fetch notes for this track, sorted by newest first
    try:
        notes_cursor = notes_collection.find(
            {'category': track}
        ).sort('_id', -1)
        notes = prepare_notes_for_template(notes_cursor)
    except Exception as e:
        print(f"❌ Error fetching notes: {e}")
        notes = []

    return render_template_string(
        STUDENT_DASHBOARD_TEMPLATE,
        track=track,
        notes=notes
    )


@app.route('/faculty/login', methods=['GET', 'POST'])
def faculty_login():
    """
    Faculty Login Portal.
    GET: Shows the login form.
    POST: Authenticates against hardcoded credentials.
    """
    # If already logged in, redirect to dashboard
    if session.get('faculty_user'):
        return redirect(url_for('faculty_dashboard'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        if username in FACULTY_CREDENTIALS and FACULTY_CREDENTIALS[username] == password:
            session['faculty_user'] = username
            flash(f"Welcome back, {username}!", "success")
            return redirect(url_for('faculty_dashboard'))
        else:
            flash("Invalid credentials. Access denied.", "error")
            return redirect(url_for('faculty_login'))

    return render_template_string(FACULTY_LOGIN_TEMPLATE)


@app.route('/faculty/logout')
def faculty_logout():
    """Clear faculty session and redirect to landing."""
    session.pop('faculty_user', None)
    flash("Logged out successfully.", "success")
    return redirect(url_for('faculty_login'))


@app.route('/faculty/dashboard')
def faculty_dashboard():
    """
    Faculty Dashboard — upload form + analytics table.
    Requires active faculty session.
    Teachers can only delete their own notes; Admins can delete any.
    """
    user = session.get('faculty_user')
    if not user:
        flash("Authentication required.", "error")
        return redirect(url_for('faculty_login'))

    # Fetch all notes sorted by newest first
    try:
        notes_cursor = notes_collection.find().sort('_id', -1)
        notes = prepare_notes_for_template(notes_cursor)
    except Exception as e:
        print(f"❌ Error fetching notes: {e}")
        notes = []

    # Calculate aggregate statistics
    total_notes = len(notes)
    total_original = sum(n.get('original_size', 0) for n in notes)
    total_optimized = sum(n.get('optimized_size', 0) for n in notes)
    total_saved = total_original - total_optimized
    total_saved_pct = f"{(total_saved / total_original * 100):.1f}" if total_original > 0 else "0.0"

    return render_template_string(
        FACULTY_DASHBOARD_TEMPLATE,
        user=user,
        notes=notes,
        tracks=TRACKS,
        total_notes=total_notes,
        total_original_fmt=format_size(total_original),
        total_optimized_fmt=format_size(total_optimized),
        total_saved_pct=total_saved_pct
    )


@app.route('/faculty/upload', methods=['POST'])
def faculty_upload():
    """
    Handle note upload with Smart Compression Engine.
    - Validates file type and size
    - Compresses images via Pillow
    - Stores file as BSON Binary in MongoDB
    """
    user = session.get('faculty_user')
    if not user:
        flash("Authentication required.", "error")
        return redirect(url_for('faculty_login'))

    # Validate form fields
    title = request.form.get('title', '').strip()
    category = request.form.get('category', '').strip()
    subject = request.form.get('subject', '').strip()

    if not title or not category or not subject:
        flash("All fields are required.", "error")
        return redirect(url_for('faculty_dashboard'))

    if category not in TRACKS:
        flash("Invalid track selected.", "error")
        return redirect(url_for('faculty_dashboard'))

    # Validate file
    if 'file' not in request.files:
        flash("No file attached.", "error")
        return redirect(url_for('faculty_dashboard'))

    file = request.files['file']
    if file.filename == '':
        flash("No file selected.", "error")
        return redirect(url_for('faculty_dashboard'))

    if not allowed_file(file.filename):
        flash(f"File type not allowed. Supported: {', '.join(sorted(ALLOWED_EXTENSIONS))}", "error")
        return redirect(url_for('faculty_dashboard'))

    try:
        # Read file data into memory
        file_data = file.read()
        original_size = len(file_data)
        filename = secure_filename(file.filename)

        # ── SMART COMPRESSION ENGINE ──
        if is_image_file(filename):
            file_data, original_size, optimized_size, filename = compress_image(file_data, filename)
        else:
            optimized_size = original_size  # Non-images: no compression

        # Store directly in MongoDB as BSON Binary
        note_doc = {
            'title': title,
            'category': category,
            'subject': subject,
            'filename': filename,
            'original_size': original_size,
            'optimized_size': optimized_size,
            'uploaded_by': user,
            'file_data': bson.Binary(file_data),
            'upload_date': datetime.utcnow()
        }

        result = notes_collection.insert_one(note_doc)
        print(f"  ✅ Stored note '{title}' (ID: {result.inserted_id}) | "
              f"Original: {format_size(original_size)} | "
              f"Optimized: {format_size(optimized_size)}")

        flash(f"Note '{title}' uploaded successfully! "
              f"Compressed: {format_size(original_size)} → {format_size(optimized_size)} "
              f"({((original_size - optimized_size) / original_size * 100):.1f}% saved)"
              if original_size > 0 else f"Note '{title}' uploaded successfully!",
              "success")

    except Exception as e:
        print(f"❌ Upload error: {e}")
        flash(f"Upload failed: {str(e)}", "error")

    return redirect(url_for('faculty_dashboard'))


@app.route('/faculty/delete/<note_id>', methods=['POST'])
def faculty_delete(note_id):
    """
    Delete a note with permission checks.
    - Teachers can ONLY delete their own notes.
    - Admins can delete ANY note.
    """
    user = session.get('faculty_user')
    if not user:
        flash("Authentication required.", "error")
        return redirect(url_for('faculty_login'))

    try:
        note = notes_collection.find_one({'_id': ObjectId(note_id)})
        if not note:
            flash("Note not found.", "error")
            return redirect(url_for('faculty_dashboard'))

        # ── PERMISSION LOGIC ──
        if user == 'admin':
            # Admin can delete any note
            pass
        elif user == 'teacher' and note.get('uploaded_by') == user:
            # Teacher can delete their own note
            pass
        else:
            flash("⛔ Permission denied. You can only delete your own notes.", "error")
            return redirect(url_for('faculty_dashboard'))

        notes_collection.delete_one({'_id': ObjectId(note_id)})
        flash(f"Note '{note.get('title', 'Unknown')}' deleted successfully.", "success")

    except Exception as e:
        print(f"❌ Delete error: {e}")
        flash(f"Delete failed: {str(e)}", "error")

    return redirect(url_for('faculty_dashboard'))


@app.route('/download/<note_id>')
def download_note(note_id):
    """
    Download a note file from MongoDB.
    Serves the (compressed) file directly from BSON Binary data.
    """
    try:
        note = notes_collection.find_one({'_id': ObjectId(note_id)})
        if not note:
            return render_template_string("""
            <!DOCTYPE html><html><head>""" + COMMON_HEAD + """</head>
            <body class="min-h-screen bg-cyber-950 text-white flex items-center justify-center">
              <div class="text-center"><h1 class="font-orbitron text-2xl gradient-text mb-4">404</h1>
              <p class="text-slate-400">Note not found.</p>
              <a href="/" class="text-amber-400 hover:underline mt-4 inline-block">Go Home</a></div>
            </body></html>
            """), 404

        file_data = note['file_data']
        filename = note['filename']
        mime_type = get_mime_type(filename)

        return send_file(
            io.BytesIO(file_data),
            mimetype=mime_type,
            as_attachment=True,
            download_name=filename
        )

    except Exception as e:
        print(f"❌ Download error: {e}")
        return render_template_string("""
        <!DOCTYPE html><html><head>""" + COMMON_HEAD + """</head>
        <body class="min-h-screen bg-cyber-950 text-white flex items-center justify-center">
          <div class="text-center"><h1 class="font-orbitron text-2xl text-red-400 mb-4">Error</h1>
          <p class="text-slate-400">Download failed.</p>
          <a href="/" class="text-amber-400 hover:underline mt-4 inline-block">Go Home</a></div>
        </body></html>
        """), 500


# ============================================================
# CUSTOM JINJA2 FILTER for regex matching in templates
# ============================================================
import re

@app.template_filter('regex_search')
def regex_search_filter(s, pattern):
    """Jinja2 filter to check if string matches regex pattern."""
    return bool(re.search(pattern, s, re.IGNORECASE))


# ============================================================
# ERROR HANDLERS
# ============================================================

@app.errorhandler(413)
def request_entity_too_large(error):
    """Handle file upload exceeding size limit."""
    flash("File too large. Maximum size is 16MB.", "error")
    return redirect(url_for('faculty_dashboard')), 413


@app.errorhandler(404)
def page_not_found(error):
    """Custom 404 page."""
    return render_template_string("""
    <!DOCTYPE html><html lang="en"><head>""" + COMMON_HEAD + """</head>
    <body class="min-h-screen bg-cyber-950 text-white cyber-grid flex items-center justify-center">
      <div class="text-center animate-fade-in">
        <h1 class="font-orbitron text-6xl font-bold gradient-text mb-4">404</h1>
        <p class="text-slate-400 text-lg mb-6">Page not found in the Warrior ERP system.</p>
        <a href="/" class="btn-glow inline-block text-white font-bold py-3 px-8 rounded-xl font-orbitron tracking-wider text-sm">RETURN HOME</a>
      </div>
    </body></html>
    """), 404


@app.errorhandler(500)
def internal_server_error(error):
    """Custom 500 page."""
    return render_template_string("""
    <!DOCTYPE html><html lang="en"><head>""" + COMMON_HEAD + """</head>
    <body class="min-h-screen bg-cyber-950 text-white cyber-grid flex items-center justify-center">
      <div class="text-center animate-fade-in">
        <h1 class="font-orbitron text-6xl font-bold text-red-400 mb-4">500</h1>
        <p class="text-slate-400 text-lg mb-6">Internal server error. The engineering team has been notified.</p>
        <a href="/" class="btn-glow inline-block text-white font-bold py-3 px-8 rounded-xl font-orbitron tracking-wider text-sm">RETURN HOME</a>
      </div>
    </body></html>
    """), 500


# ============================================================
# APPLICATION ENTRY POINT
# ============================================================
if __name__ == '__main__':
    print("\n" + "=" * 60)
    print("  ⚡ WARRIOR ERP: ULTRA PRO EDITION")
    print("  🚀 Starting server on http://0.0.0.0:8001")
    print("=" * 60 + "\n")

    # Verify MongoDB connection on startup
    try:
        client.server_info()
        print("  ✅ MongoDB Atlas: CONNECTED")
    except Exception as e:
        print(f"  ❌ MongoDB Atlas: CONNECTION FAILED — {e}")
        print("  ⚠️  The app will start but database operations will fail.")

    print("\n  📋 Routes:")
    print("     /                      — Gatekeeper Landing")
    print("     /student               — Student Track Selection")
    print("     /student/dashboard     — Student Dashboard")
    print("     /faculty/login         — Faculty Login")
    print("     /faculty/dashboard     — Faculty Dashboard")
    print("     /download/<id>         — File Download")
    print()

    app.run(host='0.0.0.0', port=8001, debug=True)