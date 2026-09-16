from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from supabase import create_client, Client
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os
import json
import uuid
import urllib.request 

app = Flask(__name__)

# 1. الحماية من الهجمات: تحديد مين يقدر يكلم الباك إند (CORS)
# (هنحط لينك Cloudflare بتاعك هنا بعد ما نرفعه، مؤقتاً هنسمح للـ localhost)
ALLOWED_ORIGIN = os.environ.get("FRONTEND_URL", "http://127.0.0.1:5500")
CORS(app, resources={r"/api/*": {"origins": ALLOWED_ORIGIN}})

# 2. إخفاء المفاتيح السرية باستخدام متغيرات البيئة (Environment Variables)
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://jyrejkuojfnlkrqnycvq.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY") # هنحط المفتاح السري في إعدادات السيرفر مش في الكود

if not SUPABASE_KEY:
    raise ValueError("Missing Supabase Key! Please set SUPABASE_KEY environment variable.")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
# ==========================================
# إعدادات رفع الملفات (الصور)
# ==========================================
UPLOAD_FOLDER = 'static/uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

@app.route('/static/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


# ==========================================
# 1. مسارات المصادقة (Auth)
# ==========================================
@app.route('/api/signup', methods=['POST'])
def signup():
    try:
        data = request.json
        name = data.get('name')
        email = data.get('email')
        phone = data.get('phone')
        password = data.get('password')

        hashed_password = generate_password_hash(password)

        response = supabase.table("users").insert({
            "name": name,
            "email": email,
            "phone": phone,
            "password": hashed_password
        }).execute()

        return jsonify({"status": "success", "message": "Account created successfully!"}), 201
    except Exception as e:
        print("SIGNUP ERROR:", str(e))
        if "duplicate key value" in str(e) or "unique" in str(e).lower():
            return jsonify({"status": "error", "message": "This Name, Email, or Phone is already registered."}), 400
        return jsonify({"status": "error", "message": "Database error: " + str(e)}), 400


@app.route('/api/login', methods=['POST'])
def login():
    try:
        data = request.json
        email = data.get('email')
        password = data.get('password')

        response = supabase.table("users").select("*").eq("email", email).execute()
        users = response.data

        if len(users) == 0:
            return jsonify({"status": "error", "message": "Email not found"}), 404

        user = users[0]

        if check_password_hash(user['password'], password):
            user.pop('password', None)
            return jsonify({
                "status": "success", 
                "message": "Login successful", 
                "data": user
            }), 200
        else:
            return jsonify({"status": "error", "message": "Incorrect password"}), 401
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# ==========================================
# 2. مسار تحديث البروفايل (Profile)
# ==========================================
@app.route('/api/profile/update', methods=['POST'])
def update_profile():
    try:
        user_id = request.form.get('id')
        primary_email = request.form.get('primary_email')
        primary_phone = request.form.get('primary_phone')
        secondary_email = request.form.get('secondary_email')
        active_email = request.form.get('active_email')
        secondary_phone = request.form.get('secondary_phone')
        active_phone = request.form.get('active_phone')

        if secondary_email:
            if secondary_email == primary_email:
                return jsonify({"status": "error", "message": "Secondary email cannot be the same as your primary email."}), 400
            check_email = supabase.table("users").select("id").or_(f"email.eq.{secondary_email},secondary_email.eq.{secondary_email}").neq("id", user_id).execute()
            if len(check_email.data) > 0:
                return jsonify({"status": "error", "message": "This secondary email is already registered."}), 400
        
        if secondary_phone:
            if secondary_phone == primary_phone:
                return jsonify({"status": "error", "message": "Secondary phone cannot be the same as your primary phone."}), 400
            check_phone = supabase.table("users").select("id").or_(f"phone.eq.{secondary_phone},secondary_phone.eq.{secondary_phone}").neq("id", user_id).execute()
            if len(check_phone.data) > 0:
                return jsonify({"status": "error", "message": "This secondary phone is already registered."}), 400

        avatar_url = request.form.get('avatar_url_existing')
        if 'avatar_file' in request.files:
            file = request.files['avatar_file']
            if file.filename != '':
                filename = secure_filename(f"avatar_{user_id}_{file.filename}")
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(file_path)
                avatar_url = f"http://127.0.0.1:5000/static/uploads/{filename}"

        update_data = {
            "avatar_url": avatar_url,
            "secondary_email": secondary_email,
            "active_email": active_email,
            "secondary_phone": secondary_phone,
            "active_phone": active_phone
        }

        response = supabase.table("users").update(update_data).eq("id", user_id).execute()
        
        if len(response.data) > 0:
            updated_user = response.data[0]
            updated_user.pop('password', None)
            return jsonify({"status": "success", "message": "Profile updated!", "data": updated_user}), 200
        else:
            return jsonify({"status": "error", "message": "User not found"}), 404
            
    except Exception as e:
        print("UPDATE ERROR:", str(e))
        return jsonify({"status": "error", "message": str(e)}), 500


# ==========================================
# 3. مسارات الفعاليات (Events)
# ==========================================
@app.route('/api/events', methods=['GET'])
def get_events():
    try:
        response = supabase.table("events").select("*").order("event_date", desc=False).execute()
        return jsonify({"status": "success", "data": response.data}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/admin/events', methods=['POST'])
@app.route('/api/admin/events', methods=['POST'])
@app.route('/api/admin/events/<event_id>', methods=['PUT'])
def update_event(event_id):
    try:
        title = request.form.get('title')
        event_date = request.form.get('event_date')
        location = request.form.get('location')
        description = request.form.get('description')

        # جلب الإيفنت القديم عشان نحافظ على الصور لو الأدمن مرفعش صور جديدة
        existing_event = supabase.table("events").select("*").eq("id", event_id).execute().data
        if not existing_event:
            return jsonify({"status": "error", "message": "Event not found"}), 404
        
        try:
            final_images = json.loads(existing_event[0].get('image_urls') or '[]')
        except:
            final_images = []

        # 1. تحديث الكافر (Cover) لو اتبعت ملف جديد
        if 'cover' in request.files:
            cover_file = request.files['cover']
            if cover_file.filename != '':
                filename = secure_filename(f"cover_{uuid.uuid4().hex}_{cover_file.filename}")
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                cover_file.save(file_path)
                new_cover_url = f"http://127.0.0.1:5000/static/uploads/{filename}"
                
                # استبدال أول صورة (الكافر)
                if len(final_images) > 0:
                    final_images[0] = new_cover_url
                else:
                    final_images.append(new_cover_url)

        # 2. تحديث الجاليري (Gallery) لو اتبعت ملفات جديدة
        if 'images' in request.files:
            files = request.files.getlist('images')
            if len(files) > 0 and files[0].filename != '':
                new_gallery = []
                for file in files[:5]: 
                    if file.filename != '':
                        filename = secure_filename(f"gallery_{uuid.uuid4().hex}_{file.filename}")
                        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                        file.save(file_path)
                        new_gallery.append(f"http://127.0.0.1:5000/static/uploads/{filename}")
                
                # نحتفظ بالكافر القديم (أول صورة) ونبدل باقي الجاليري
                if len(final_images) > 0:
                    final_images = [final_images[0]] + new_gallery
                else:
                    final_images = new_gallery

        update_data = {
            "title": title,
            "description": description,
            "event_date": event_date,
            "location": location,
            "image_urls": json.dumps(final_images)
        }

        supabase.table("events").update(update_data).eq("id", event_id).execute()
        return jsonify({"status": "success", "message": "Event Updated!"}), 200
    except Exception as e:
        print("EVENT UPDATE ERROR:", str(e))
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/events/<event_id>', methods=['DELETE'])
def delete_event(event_id):
    try:
        data = request.json
        user_role = data.get('role')

        # صلاحية المسح للأدمن فقط
        if user_role != 'admin':
            return jsonify({"status": "error", "message": "Unauthorized: Only admins can delete events!"}), 403

        # مسح الحضور أولاً ثم الفعالية
        supabase.table("attendees").delete().eq("event_id", event_id).execute()
        supabase.table("events").delete().eq("id", event_id).execute()

        return jsonify({"status": "success", "message": "Event deleted successfully!"}), 200
    except Exception as e:
        print("DELETE ERROR:", str(e))
        return jsonify({"status": "error", "message": str(e)}), 500


# ==========================================
# 4. مسارات الحضور (RSVPs)
# ==========================================
@app.route('/api/rsvp', methods=['POST'])
def rsvp():
    try:
        data = request.json
        full_name = data.get('name')
        email = data.get('email')
        phone = data.get('phone')
        event_id = data.get('event_id')

        print(f"👉 Received RSVP for: {full_name}, Event ID: {event_id}")

        # 1. تسجيل الحضور في قاعدة البيانات
        response = supabase.table("attendees").insert({
            "full_name": full_name,
            "email": email,
            "phone_number": phone,
            "event_id": event_id
        }).execute()
        
        print("✅ Saved to Supabase successfully!")

        # 2. جلب بيانات الفعالية
        event_data = supabase.table("events").select("*").eq("id", event_id).execute()
        
        if event_data.data:
            event = event_data.data[0]
            print(f"📦 Found Event: {event.get('title')}")
            
            # اللينك بتاع الـ Webhook في n8n (تم تعديله للـ Production)
            webhook_url = "https://418733e8.kube-ops.com/webhook/3c22f766-4008-4f5f-a375-1d7c5fb1f80f"
            payload = {
                "attendee": {
                    "name": full_name, 
                    "email": email, 
                    "phone": phone
                },
                "event": {
                    "title": event.get("title"), 
                    "date": event.get("event_date"), 
                    "location": event.get("location"), 
                    "description": event.get("description")
                }
            }
            
            # 3. ضرب الـ Webhook مع تخطي الحماية
            try:
                print("🚀 Sending to n8n...")
                data_bytes = json.dumps(payload).encode('utf-8')
                
                # الـ Headers دي بتوهم السيرفر إن الطلب جي من متصفح جوجل كروم عشان ميعملش 403
                headers = {
                    'Content-Type': 'application/json',
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                }
                
                req = urllib.request.Request(webhook_url, data=data_bytes, headers=headers, method='POST')
                webhook_response = urllib.request.urlopen(req, timeout=10)
                print(f"🎯 n8n Received the data! Status code: {webhook_response.getcode()}")
            except Exception as req_err:
                print("❌ n8n Error:", req_err)
        else:
            print("⚠️ Event not found in database to send to n8n.")

        return jsonify({"status": "success", "message": "Spot Confirmed Successfully! 🎉"}), 200
        
    except Exception as e:
        print("🔥 General Error:", str(e))
        if "unique_rsvp" in str(e) or "duplicate key" in str(e).lower():
            return jsonify({"status": "error", "message": "You are already registered for this event! 👍"}), 400
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/admin/rsvps/<event_id>', methods=['GET'])
def get_rsvps(event_id):
    try:
        response = supabase.table("attendees").select("*").eq("event_id", event_id).execute()
        return jsonify({"status": "success", "data": response.data}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True, port=5000)