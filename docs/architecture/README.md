# DIP Studio — Architecture Documentation

هذه الحزمة توثق التصميم المعماري المقترح لمشروع **DIP Studio**: محرر صور مكتبي احترافي يجمع تجربة تحرير شبيهة بالمحررات الاحترافية مع محرك Digital Image Processing متكامل وإمكانات Computer Vision.

## المبادئ
- المستخدم يتعامل مع Tool، والـ Tool يتعامل مع Algorithm.
- الخوارزميات لا توضع داخل واجهة المستخدم.
- Mouse وKeyboard يستعملان نفس Command System.
- الـ Domain مستقل قدر الإمكان عن Qt وOpenCV.
- المعالجة غير التدميرية هي الافتراضية حيثما أمكن.
- Rendering منفصل عن Processing.
- البيانات المشتركة تديرها DataStore مع Copy-on-Write وCaching.
- النظام مصمم للتوسع بالـ plugins دون تعديل جوهري في MainWindow.

## الوثائق
1. `01-project-vision-and-scope.md` — الرؤية والنطاق والأهداف الأكاديمية.
2. `02-technology-and-system-architecture.md` — التقنيات والطبقات والاعتماديات.
3. `03-professional-ui-ux-workspace.md` — تجربة المستخدم وWorkspace والواجهة الاحترافية.
4. `04-domain-data-model.md` — نموذج المجال والوثائق والعناصر.
5. `05-memory-data-store-and-caching.md` — الذاكرة والـ DataStore والـ Cache والـ Tiles.
6. `06-layers-masks-selections-text.md` — الطبقات والأقنعة والتحديد والنص والأشكال.
7. `07-dip-processing-engine-and-library-stack.md` — محرك DIP ومكتبات المعالجة.
8. `08-tools-commands-parameters-and-history.md` — الأدوات والأوامر والمعلمات والتاريخ.
9. `09-keyboard-shortcuts-and-input-system.md` — نظام الاختصارات والإدخال والسياق.
10. `10-import-export-and-file-format.md` — الاستيراد والتصدير وصيغة المشروع.
11. `11-rendering-performance-and-concurrency.md` — Rendering والأداء والتزامن والإلغاء.
12. `12-computer-vision-extensibility-testing-roadmap.md` — Computer Vision والإضافات والاختبارات وخارطة الطريق.

## النتيجة المستهدفة
DIP Studio ليس مجرد واجهة فوق OpenCV، بل منصة معالجة صور قابلة للتوسع: Libraries تقدم الخوارزميات، Processing Engine يوحد العقود، Domain يحفظ النموذج القابل للتحرير، Application يدير الأوامر، PySide6 يقدم التفاعل المكتبي، وRender Engine يعرض النتيجة.
