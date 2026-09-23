---
title: الوظائف الحالية ومكان الوصول إليها
order: 4
category: دليل المستخدم
direction: rtl
lang: ar
icon: document
summary: مرجع عملي للقوائم والوظائف المتاحة حاليًا في DIP Studio
---

# الوظائف الحالية ومكان الوصول إليها

هذه الصفحة مرجع سريع للوظائف الموجودة في الواجهة الحالية. أسماء الأوامر مكتوبة كما تظهر في القوائم، حتى يسهل العثور عليها.

## File — ملف

- **New:** إنشاء مشروع جديد. المكان: **File > New** أو **Ctrl+N**.
- **Open project...:** فتح مشروع محفوظ. المكان: **File > Open project...**.
- **Save project:** حفظ المشروع. المكان: **File > Save project** أو **Ctrl+S**.
- **Open Image...:** فتح صورة في مستند. المكان: **File > Open Image...**.
- **Place Image as Layer...:** إضافة صورة كطبقة جديدة. المكان: **File > Place Image as Layer...**.
- **Export As...:** تصدير الصورة بصيغة PNG أو JPEG أو BMP أو TIFF أو PPM. المكان: **File > Export As...**.
- **Exit:** إغلاق التطبيق. المكان: **File > Exit**.

## View — عرض

- **Toggle theme:** تبديل المظهر.
- **Command palette:** البحث عن الأوامر وتشغيلها. المكان: **View > Command palette** أو **Ctrl+Shift+P**.
- **Keyboard shortcuts:** عرض الاختصارات وتعديل الاختصارات القابلة للتخصيص. المكان: **View > Keyboard shortcuts**.
- **Shortcut profile:** اختيار ملف اختصارات من **View > Shortcut profile**.
- **Workspace sidebar:** إظهار أو إخفاء لوحات مساحة العمل.
- **Zoom in / Zoom out:** تكبير الصورة أو تصغيرها. الاختصاران **+** و**-**.
- **Fit canvas:** ملاءمة الصورة داخل مساحة العرض.
- **Actual size:** عرض الصورة بحجمها الفعلي.
- **Show grid:** إظهار الشبكة أو إخفاؤها.
- **Before/after:** تشغيل أو إيقاف مقارنة قبل التعديل وبعده.

## Edit — تحرير

- **Undo / Redo:** التراجع والإعادة. الاختصاران **Ctrl+Z** و**Ctrl+Y**.
- **Add layer:** إضافة طبقة. المكان: **Edit > Add layer** أو **Ctrl+Shift+N** عندما تكون لوحة Layers نشطة.
- **Duplicate layer:** نسخ الطبقة. المكان: **Edit > Duplicate layer** أو **Ctrl+J**.
- **Remove selected layers:** حذف الطبقات المحددة. المكان: **Edit > Remove selected layers** أو **Delete**.
- **Move layer up / Move layer down:** تغيير ترتيب الطبقة.
- **Toggle layer visibility:** إظهار الطبقة أو إخفاؤها.
- **Rename selected layer:** إعادة تسمية الطبقة أو الضغط على **F2** داخل لوحة Layers.
- **Copy selected layers / Paste layers / Cut selection or selected layers:** نسخ ولصق وقص الطبقات أو التحديد. الاختصارات **Ctrl+C** و**Ctrl+V** و**Ctrl+X**.
- **Copy and paste in place:** نسخ المحتوى في موضعه نفسه. الاختصار **Ctrl+K**.

## Window — نافذة

- **Workspace:** إظهار مساحة العمل.
- **Properties:** خصائص الأداة أو الطبقة المحددة.
- **Layers:** قائمة الطبقات وترتيبها وتحديدها.
- **Channels:** عرض القنوات المتاحة.
- **Navigator:** معاينة موضع الصورة أثناء التكبير.
- **History:** الانتقال بين خطوات التعديل السابقة.
- **Save workspace:** حفظ ترتيب اللوحات.
- **Reset workspace:** إعادة ترتيب اللوحات إلى الوضع الافتراضي.

## Image — صورة

- **Rotate 90° CW:** تدوير 90 درجة مع عقارب الساعة.
- **Rotate 90° CCW:** تدوير 90 درجة عكس عقارب الساعة.
- **Rotate 180°:** تدوير 180 درجة.
- **Flip Horizontal:** قلب أفقي.
- **Flip Vertical:** قلب رأسي.

كل هذه الأوامر موجودة في قائمة **Image** وتعمل على المستند المفتوح.

## Layer — طبقة

توفر قائمة **Layer** الأوامر الأساسية لإضافة الطبقات ونسخها ودمجها وحذفها وتغيير ظهورها واسمها. اختر طبقة أولًا من لوحة **Layers**، ثم استخدم **Layer > Add layer** أو **Duplicate layer** أو **Merge down** أو **Remove** أو أوامر الظهور وإعادة التسمية.

## Select — تحديد

- **Select All:** تحديد الصورة كاملة.
- **Deselect:** إزالة التحديد.

توجد أدوات إنشاء التحديد في **Tools > Selection**، وهي التحديد المستطيل والبيضاوي والحر والمضلع والتحديد حسب اللون.

## Filter — مرشحات

توجد المرشحات في **Filter**، وبعضها يفتح لوحة Properties لإدخال القيم:

- **Blur:** Gaussian Blur وMedian Blur وBilateral Filter وMean Filter.
- **Edges:** Sobel وCanny وLaplacian.
- **Adjust:** Negative وGamma وLog Transform وBrightness & Contrast.
- **Histogram:** Equalize وCLAHE.
- **Morphology:** Erode وDilate وOpen وClose.
- **Color:** Grayscale وHue & Saturation.

اختر المرشح، عدل القيم في Properties عند ظهورها، ثم طبق العملية من اللوحة.

## Analysis — تحليل

- **Histogram:** عرض توزيع درجات السطوع.
- **Image Statistics:** عرض معلومات الصورة وإحصاءات القنوات.
- **Threshold...:** إنشاء معاينة للعتبة الثنائية.
- **Segment...:** تقسيم مناطق الصورة.

تصل إلى هذه الوظائف من قائمة **Analysis**، وقد تحتاج إلى فتح صورة وتحديد طبقة تحتوي على بيانات صورة.

## Tools — أدوات

تجمع قائمة **Tools** الأدوات حسب الفئة:

- **General:** Select.
- **Selection:** Selection وEllipse selection وLasso وPolygon selection وColor selection.
- **Transform:** Crop وMove وTransform وRotate.
- **Filter:** Blur وEdge.
- **Paint:** Gradient وBrush وPencil وEraser وFill.
- **Retouch:** Clone stamp.
- **Navigation:** Hand وZoom.
- **Sampling:** Eyedropper.
- **Vector:** Text.
- **Drawing:** Rectangle وEllipse وLine وPolygon.
- **Analysis:** Histogram وThreshold وMorphology وSegmentation.

اختصارات الأدوات مذكورة بجانبها في صفحة **الاختصارات** وفي أزرار شريط الأدوات.

## Help — مساعدة

- **User Guide...:** فتح دليل المستخدم، أو اضغط **F1**.
- **About DIP Studio:** عرض معلومات التطبيق.

> [!NOTE]
> قد تكون بعض الأوامر غير متاحة عندما لا يوجد مستند مفتوح أو لا توجد طبقة محددة. هذا سلوك طبيعي؛ افتح صورة أو مشروعًا وحدد الطبقة ثم أعد المحاولة.
