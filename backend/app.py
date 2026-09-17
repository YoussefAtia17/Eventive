from flask import Flask, request, jsonify
from flask_cors import CORS
from supabase import create_client, Client
from werkzeug.utils import secure_filename
import os
import json
import uuid

app = Flask(__name__)

# السماح للفرونت إند إنه يكلم الباك إند من أي مكان
CORS(app, resources={r"/api/*": {"origins": "*"}})

# متغيرات البيئة اللي حطيناها في Vercel
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("Warning: Supabase keys are missing!")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ----------------- EVENTS ENDPOINTS -----------------

@app.route('/api/events', methods=['GET'])
def get_events():
    try:
        response = supabase.from_("events").select("*").execute()
        return jsonify({"status": "success", "data": response.data}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/admin/events', methods=['POST'])
def create_event():
    try:
        title = request.form.get('title')
        event_date = request.form.get('event_date')
        location = request.form.get('location')
        description = request.form.get('description')
        created_by = request.form.get('created_by')

        image_urls = []
        
        # 1. رفع صورة الكافر (Cover) لـ Supabase Storage
        if 'cover' in request.files:
            cover_file = request.files['cover']
            if cover_file.filename != '':
                filename = secure_filename(f"cover_{uuid.uuid4().hex}_{cover_file.filename}")
                file_bytes = cover_file.read()
                
                # الرفع على باكت اسمه 'events'
                supabase.storage.from_("events").upload(
                    file=file_bytes, 
                    path=filename, 
                    file_options={"content-type": cover_file.content_type}
                )
                cover_url = supabase.storage.from_("events").get_public_url(filename)
                image_urls.append(cover_url)

        # 2. رفع صور المعرض (Gallery) لـ Supabase Storage
        if 'images' in request.files:
            files = request.files.getlist('images')
            for file in files[:5]: 
                if file.filename != '':
                    filename = secure_filename(f"gallery_{uuid.uuid4().hex}_{file.filename}")
                    file_bytes = file.read()
                    
                    supabase.storage.from_("events").upload(
                        file=file_bytes, 
                        path=filename, 
                        file_options={"content-type": file.content_type}
                    )
                    url = supabase.storage.from_("events").get_public_url(filename)
                    image_urls.append(url)

        response = supabase.table("events").insert({
            "title": title,
            "description": description,
            "event_date": event_date,
            "location": location,
            "image_urls": json.dumps(image_urls),
            "created_by": created_by
        }).execute()

        return jsonify({"status": "success", "message": "Event Created!"}), 201
    except Exception as e:
        print("EVENT CREATE ERROR:", str(e))
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/admin/events/<event_id>', methods=['PUT'])
def update_event(event_id):
    try:
        title = request.form.get('title')
        event_date = request.form.get('event_date')
        location = request.form.get('location')
        description = request.form.get('description')

        existing_event = supabase.table("events").select("*").eq("id", event_id).execute().data
        if not existing_event:
            return jsonify({"status": "error", "message": "Event not found"}), 404
        
        try:
            final_images = json.loads(existing_event[0].get('image_urls') or '[]')
        except:
            final_images = []

        if 'cover' in request.files:
            cover_file = request.files['cover']
            if cover_file.filename != '':
                filename = secure_filename(f"cover_{uuid.uuid4().hex}_{cover_file.filename}")
                supabase.storage.from_("events").upload(
                    file=cover_file.read(), 
                    path=filename, 
                    file_options={"content-type": cover_file.content_type}
                )
                new_cover_url = supabase.storage.from_("events").get_public_url(filename)
                
                if len(final_images) > 0:
                    final_images[0] = new_cover_url
                else:
                    final_images.append(new_cover_url)

        if 'images' in request.files:
            files = request.files.getlist('images')
            if len(files) > 0 and files[0].filename != '':
                new_gallery = []
                for file in files[:5]: 
                    if file.filename != '':
                        filename = secure_filename(f"gallery_{uuid.uuid4().hex}_{file.filename}")
                        supabase.storage.from_("events").upload(
                            file=file.read(), 
                            path=filename, 
                            file_options={"content-type": file.content_type}
                        )
                        new_url = supabase.storage.from_("events").get_public_url(filename)
                        new_gallery.append(new_url)
                
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
        if data.get('role') != 'admin':
            return jsonify({"status": "error", "message": "Unauthorized"}), 403
            
        supabase.table("rsvps").delete().eq("event_id", event_id).execute()
        supabase.table("events").delete().eq("id", event_id).execute()
        
        return jsonify({"status": "success", "message": "Event deleted"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# ----------------- RSVP & AUTH ENDPOINTS (باقي الأكواد القديمة) -----------------

@app.route('/api/rsvp', methods=['POST'])
def rsvp():
    try:
        data = request.json
        # Check if already RSVPed
        existing = supabase.table("rsvps").select("*").eq("email", data['email']).eq("event_id", data['event_id']).execute()
        if existing.data:
            return jsonify({"status": "error", "message": "You have already RSVP'd for this event."}), 400
            
        supabase.table("rsvps").insert({
            "full_name": data['name'],
            "email": data['email'],
            "phone_number": data.get('phone', ''),
            "event_id": data['event_id']
        }).execute()
        return jsonify({"status": "success", "message": "Spot Booked Successfully!"}), 201
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/admin/rsvps/<event_id>', methods=['GET'])
def get_event_rsvps(event_id):
    try:
        response = supabase.table("rsvps").select("*").eq("event_id", event_id).execute()
        return jsonify({"status": "success", "data": response.data}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/signup', methods=['POST'])
def signup():
    try:
        data = request.json
        response = supabase.table("users").insert({
            "email": data['email'],
            "password_hash": str(data['password']), 
            "full_name": data['name'],
            "phone_number": data.get('phone', ''),
            "role": "user"
        }).execute()
        return jsonify({"status": "success", "message": "User created"}), 201
    except Exception as e:
        if 'duplicate key value' in str(e):
            return jsonify({"status": "error", "message": "Email already exists"}), 400
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/login', methods=['POST'])
def login():
    try:
        data = request.json
        response = supabase.table("users").select("*").eq("email", data['email']).execute()
        if not response.data:
            return jsonify({"status": "error", "message": "User not found"}), 404
            
        user = response.data[0]
        if user['password_hash'] != str(data['password']):
            return jsonify({"status": "error", "message": "Invalid password"}), 401
            
        # ضفنا هنا كل البيانات الجديدة عشان ترجع للواجهة
        user_data = {
            "id": user.get('id'),
            "name": user.get('full_name', ''),
            "email": user.get('email', ''),
            "phone": user.get('phone_number', ''),
            "role": user.get('role', 'user'),
            "avatar_url": user.get('avatar_url', ''),
            "secondary_email": user.get('secondary_email', ''),
            "secondary_phone": user.get('secondary_phone', ''),
            "active_email": user.get('active_email', 'primary'),
            "active_phone": user.get('active_phone', 'primary')
        }
        return jsonify({"status": "success", "data": user_data}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/update', methods=['POST', 'PUT'])
def update_profile():
    try:
        # الواجهة بتبعت الإيميل الأساسي عشان نعرف نحدث بيانات مين
        email = request.form.get('email') or request.json.get('email')
        if not email:
            return jsonify({"status": "error", "message": "Email is required"}), 400

        update_data = {}
        
        # لو الواجهة باعتة بيانات نصية إضافية
        if request.form.get('secondary_email'):
            update_data['secondary_email'] = request.form.get('secondary_email')
        if request.form.get('secondary_phone'):
            update_data['secondary_phone'] = request.form.get('secondary_phone')

        # التعامل مع رفع الصورة
        file = request.files.get('avatar') or request.files.get('file') or request.files.get('profile_picture')
        if file and file.filename != '':
            filename = secure_filename(f"avatar_{uuid.uuid4().hex}_{file.filename}")
            
            # الرفع على باكت avatars
            supabase.storage.from_("avatars").upload(
                file=file.read(), 
                path=filename, 
                file_options={"content-type": file.content_type}
            )
            update_data['avatar_url'] = supabase.storage.from_("avatars").get_public_url(filename)

        if update_data:
            supabase.table("users").update(update_data).eq("email", email).execute()
        
        return jsonify({"status": "success", "message": "Profile updated!"}), 200
    except Exception as e:
        print("UPDATE ERROR:", str(e))
        return jsonify({"status": "error", "message": str(e)}), 500
    
if __name__ == '__main__':
    app.run(debug=True)