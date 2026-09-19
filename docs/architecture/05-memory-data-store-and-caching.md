# 05 — Memory, DataStore and Caching

## 1. المشكلة
الصور الكبيرة تستهلك الذاكرة بسرعة. مثال تقريبي: صورة 6000×4000 RGBA بصيغة float32 تحتاج نحو 384 MB للنسخة الواحدة.

لذلك لا يجوز أن تنشئ كل عملية نسخة كاملة من الصورة بلا حاجة.

## 2. DataStore
```text
DataStore
 ├── ImageBuffers
 ├── MaskBuffers
 ├── TileStore
 ├── PreviewCache
 └── ProcessingCache
```

Layers تشير إلى البيانات بدلاً من امتلاك نسخ مستقلة غير منضبطة.

## 3. Copy-on-Write
إذا كانت عدة مراجع تشترك في buffer فلا يتم نسخه إلا عند الحاجة إلى mutation.

```text
Shared Buffer
     ↓
Read → no copy
Write → detach/copy
```

## 4. Non-destructive Processing
بدلاً من تخزين الصورة كاملة بعد كل Filter:
```text
Source
 ↓
Operation 1
 ↓
Operation 2
 ↓
Operation 3
```

يمكن إعادة التقييم عند الحاجة، مع Cache للنتائج.

## 5. Cache Key
مفهوم مفتاح مناسب:
```text
input_version
+ processor_id
+ normalized_parameters
+ mask_version
+ selection_version
```

إذا لم يتغير المدخل أو المعلمات يمكن إعادة استخدام النتيجة.

## 6. Preview Cache
الـ Preview لا يجب أن يكون دائماً full resolution. يمكن تشغيل المعالجة على نسخة مصغرة ثم تنفيذ full resolution عند Apply.

## 7. Tile Processing
من البداية يجب تصميم abstraction يدعم tiles حتى لو كان الإصدار الأول يستخدم ndarray كاملة.

أحجام مناسبة كبداية:
- 256×256
- 512×512

الفكرة:
```text
Image
 ├── Tile
 ├── Tile
 ├── Tile
 └── Tile
```

ويتم تحميل أو معالجة الأجزاء المطلوبة فقط عند الحاجة.

## 8. Memory Tiers
```text
RAM
 ├── active buffers
 ├── visible tiles
 └── current preview

Cache
 ├── processor results
 ├── rendered tiles
 └── previews

Disk
 ├── assets
 ├── project
 └── recovery/autosave
```

## 9. History
History يخزن Commands أو state transitions وليس صوراً كاملة بعد كل خطوة. يمكن استعمال checkpoints عندما يصبح إعادة الحساب مكلفاً.

## 10. النتيجة
هذا التصميم يجعل النظام قابلاً للتعامل مع صور كبيرة دون أن يصبح كل Filter سبباً في انفجار استهلاك RAM.
