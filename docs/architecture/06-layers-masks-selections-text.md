# 06 — Layers, Masks, Selections, Text and Shapes

## 1. Layers
الطبقات هي أساس التحرير غير التدميري.

أنواعها:
- ImageLayer
- AdjustmentLayer
- FilterLayer
- TextLayer
- ShapeLayer
- GroupLayer

كل Layer يملك visibility وlock وopacity وblend mode وtransform ومراجع للمحتوى والقناع.

## 2. Masks
```text
Mask
 ├── id
 ├── dimensions
 ├── mode
 └── buffer_reference
```

Soft mask يستخدم قيماً بين 0 و1 لتمثيل مقدار التأثير.

العمليات:
- create
- edit
- invert
- disable
- delete
- apply
- feather
- blur
- copy

## 3. Selection مقابل Mask
Selection هو مفهوم تحريري/تفاعلي يحدد منطقة العمل، بينما Mask هو تمثيل قابل لإعادة الاستخدام لتأثير أو شفافية.

```text
Selection
    ↓
Rasterized Mask
    ↓
Processor
```

Selections يجب أن تدعم:
- rectangle (مع مفتاح `Shift` لنسبة 1:1 مربع ومفتاح `Alt` للمركز)
- ellipse (مع مفتاح `Shift` لنسبة 1:1 دائرة كاملة ومفتاح `Alt` للمركز)
- lasso (تحديد حر بالأيدي)
- polygon (تحديد مضلع بالنقر)
- color-based / Magic Wand (تحديد الألوان المتصلة حسب السماحية tolerance)
- object-based (future feature)
- add/subtract/intersect/invert
- feather
- expand/contract
- copy/paste/cut (متاحان كـ Layer via Copy / Layer via Cut)

## 4. TextLayer
النص يجب أن يكون **First-Class Layer** وليس صورة يتم rasterize لها مباشرة.

```text
TextLayer
 ├── content
 ├── font_family
 ├── font_size
 ├── weight
 ├── style
 ├── color
 ├── alignment
 ├── direction
 ├── letter_spacing
 ├── line_spacing
 ├── stroke (future feature)
 ├── shadow (future feature)
 ├── background
 └── transform
```

يجب دعم multiline وRTL/LTR لأن المشروع يتعامل مع العربية.

القاعدة: يبقى النص قابلاً للتحرير حتى يطلب المستخدم rasterization أو يحتاج التصدير إلى صيغة لا تحفظ البنية.

## 5. ShapeLayer
يمكن أن يحتوي:
- rectangle
- ellipse
- polygon
- line
- custom path

ويمكن الاحتفاظ به كبيانات هندسية بدلاً من rasterizing مبكر.

## 6. الترتيب المفاهيمي
```text
Project
 └── Document
      └── LayerTree
           ├── Group
           │    ├── ImageLayer
           │    ├── TextLayer
           │    └── ShapeLayer
           └── Adjustment/Filter Layers
```

## 7. الفائدة الأكاديمية
هذا النموذج يسمح بإجراء معالجة DIP على صورة كاملة أو على Layer أو Selection أو Mask دون إعادة تصميم الخوارزمية لكل حالة.
