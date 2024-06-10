from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import os
from PIL import Image
import piexif
import sqlite3

app = FastAPI()
UPLOAD_FOLDER = 'images'

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

DATABASE = 'metadata.db'

# Initialize database
def init_db():
    with sqlite3.connect(DATABASE) as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS images (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL,
                date_time TEXT,
                location TEXT
            )
        ''')
init_db()

class ImageMetadata(BaseModel):
    id: int
    filename: str
    date_time: Optional[str]
    location: Optional[str]
    url: str

def extract_metadata(file_path):
    image = Image.open(file_path)
    if 'exif' not in image.info:
        return {
            'filename': os.path.basename(file_path),
            'date_time': None,
            'location': None
        }
    
    exif_data = piexif.load(image.info['exif'])
    date_time = exif_data['0th'].get(piexif.ImageIFD.DateTime, b'').decode('utf-8')
    gps_info = exif_data['GPS']
    location = None
    if gps_info:
        gps_latitude = gps_info.get(piexif.GPSIFD.GPSLatitude)
        gps_latitude_ref = gps_info.get(piexif.GPSIFD.GPSLatitudeRef)
        gps_longitude = gps_info.get(piexif.GPSIFD.GPSLongitude)
        gps_longitude_ref = gps_info.get(piexif.GPSIFD.GPSLongitudeRef)
        
        if gps_latitude and gps_longitude:
            lat = gps_latitude[0] + gps_latitude[1]/60.0 + gps_latitude[2]/3600.0
            if gps_latitude_ref != 'N':
                lat = -lat
            lon = gps_longitude[0] + gps_longitude[1]/60.0 + gps_longitude[2]/3600.0
            if gps_longitude_ref != 'E':
                lon = -lon
            location = f"{lat},{lon}"
    
    return {
        'filename': os.path.basename(file_path),
        'date_time': date_time,
        'location': location
    }

@app.get("/", response_class=HTMLResponse)
async def read_index():
    with open("index.html") as f:
        html_content = f.read()
    return HTMLResponse(content=html_content)

@app.get("/upload")
async def read_upload():
    with open("upload.html") as f:
        html_content = f.read()
    return HTMLResponse(content=html_content)

@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No selected file")
    
    extension = os.path.splitext(file.filename)[1]
    
    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.execute('''
            INSERT INTO images (filename, date_time, location)
            VALUES (?, ?, ?)
        ''', (file.filename, None, None))
        image_id = cursor.lastrowid

    new_filename = f"{image_id}{extension}"
    file_path = os.path.join(UPLOAD_FOLDER, new_filename)
    
    with open(file_path, "wb") as f:
        f.write(await file.read())
    
    metadata = extract_metadata(file_path)
    
    with sqlite3.connect(DATABASE) as conn:
        conn.execute('''
            UPDATE images
            SET filename = ?, date_time = ?, location = ?
            WHERE id = ?
        ''', (new_filename, metadata['date_time'], metadata['location'], image_id))
    
    return {"message": "File uploaded successfully", "id": image_id, "filename": new_filename}

@app.get("/images/{filename}")
async def get_image(filename: str):
    file_path = os.path.join(UPLOAD_FOLDER, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(file_path)

@app.get("/images", response_model=List[ImageMetadata])
async def get_all_images():
    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.execute("SELECT id, filename, date_time, location FROM images")
        results = cursor.fetchall()
    
    images = [{"id": row[0], "filename": row[1], "date_time": row[2], "location": row[3], "url": f"/images/{row[1]}"} for row in results]
    return images

@app.get("/search", response_model=List[ImageMetadata])
async def search_images(date: Optional[str] = None, location: Optional[str] = None):
    query = "SELECT id, filename, date_time, location FROM images WHERE 1=1"
    params = []
    
    if date:
        query += " AND date_time LIKE ?"
        params.append(f"%{date}%")
    
    if location:
        query += " AND location = ?"
        params.append(location)
    
    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.execute(query, params)
        results = cursor.fetchall()
    
    images = [{"id": row[0], "filename": row[1], "date_time": row[2], "location": row[3], "url": f"/images/{row[1]}"} for row in results]
    return images

# Enable CORS (allow from all origins)
origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=8000)
