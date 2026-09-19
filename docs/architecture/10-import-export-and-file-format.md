# 10 — Import, Export and File Format

## 1. IO Architecture
```text
IOManager
 ├── ImportManager
 ├── ExportManager
 └── FormatRegistry
```

## 2. Initial Image Formats
- PNG
- JPEG/JPG
- BMP
- TIFF
- WebP
- GIF حيث يكون دعمه ذا معنى

امتدادات متقدمة لاحقاً:
- RAW
- HDR
- EXR
- SVG

## 3. Import Pipeline
```text
File
 ↓
Format Detector
 ↓
Importer
 ↓
ImageData
 ↓
DataStore
 ↓
Document
 ↓
ImageLayer
```

يجب استخراج metadata مثل:
- width
- height
- channels
- bit depth
- color space
- alpha
- DPI/resolution
- metadata

## 4. Open vs Place
**Open Image** ينشئ Document جديداً.

**Import/Place** يضيف الصورة إلى Document قائم كـ Layer أو Asset بحسب العملية.

هذا الفرق مهم في تجربة المستخدم.

## 5. Export Pipeline
```text
Document
 ↓
Render Engine
 ↓
Final Composite
 ↓
Export Pipeline
 ↓
Encoder
 ↓
File
```

## 6. Format Options
### PNG
transparency, bit depth, compression, metadata

### JPEG
quality, subsampling, metadata

### TIFF
bit depth, compression, alpha, color space

## 7. Project Format
صيغة المشروع المقترحة: `.dip`

```text
project.dip
 ├── project metadata
 ├── documents
 ├── assets
 ├── thumbnails
 ├── previews
 └── recovery data
```

يجب أن تحفظ البنية القابلة للتحرير، وليس مجرد الصورة النهائية:
- layer tree
- text
- masks
- selections
- operations
- processing graph
- objects
- workspace
- metadata

## 9. CV Export
عند الحاجة:
- JSON
- CSV
- XML

مثلاً tracking:
```text
object_id
frame
timestamp
x
y
```

## 10. Format Registry
```text
Format
 ├── extension
 ├── MIME type
 ├── importer
 ├── exporter
 └── capabilities
```
