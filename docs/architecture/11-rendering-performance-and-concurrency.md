# 11 — Rendering, Performance and Concurrency

## 1. Rendering منفصل عن Processing
المعالجة تنتج بيانات، بينما Rendering يحول حالة Document إلى صورة معروضة على Canvas.

```text
Document
 ↓
Render Graph
 ↓
Layer Evaluation
 ↓
Masks
 ↓
Transforms
 ↓
Blend Modes
 ↓
Composite
 ↓
QImage / QPixmap
 ↓
Canvas
```

## 2. لماذا الفصل مهم؟
لأن Filter ليس هو طريقة عرض الصورة، ويمكن أن تتغير طريقة العرض دون إعادة تعريف الخوارزمية.

## 3. UI Thread
UI thread يجب ألا ينفذ معالجة ثقيلة.

```text
UI Thread
   ↓
Processing Job
   ↓
Worker
   ↓
Processor
   ↓
Result Signal
   ↓
UI
```

## 4. Background Processing
العمليات الثقيلة مثل:
- large convolution
- FFT
- restoration
- segmentation
- detection
- tracking

تعمل في الخلفية، مع progress وcancellation عندما يكون ذلك ممكناً.

## 5. Cancellation
كل ProcessingContext طويل الأمد يمكن أن يحتوي Cancellation Token. Processor يجب أن يتحقق منه في نقاط مناسبة بدلاً من ترك المستخدم ينتظر عملية لا يمكن إيقافها.

## 6. Progressive Processing
للعمليات المكلفة:
```text
Low Resolution Preview
        ↓
Intermediate Result
        ↓
Full Resolution
```

وهذا يحسن الإحساس بسرعة التطبيق.

## 7. Caching
يجب تخزين:
- processor results
- rendered tiles
- previews

مع invalidation مبني على input/version/parameters.

## 8. Tiles
Render Engine يجب أن يكون قابلاً للتوسع إلى tile-based rendering، حتى لو كانت البداية تعتمد على full-image arrays.

## 9. GPU Extension Point
يمكن لاحقاً إضافة:
- OpenCV CUDA
- CuPy
- GPU-specific backends

من دون إعادة كتابة Domain، لأن GPU يجب أن يكون Backend للـ Processing وليس جزءاً من نموذج المجال.

## 10. قواعد الأداء
- تجنب نسخ الصور بلا سبب.
- استعمال views عندما تكون آمنة.
- Copy-on-Write عند mutation.
- preview منخفض الدقة.
- background jobs.
- cache.
- tiles.
- checkpoints عند الحاجة.
- قياس الأداء عبر benchmarks بدلاً من التخمين.
