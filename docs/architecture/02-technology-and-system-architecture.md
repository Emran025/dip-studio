# 02 — Technology and System Architecture

## 1. Technology Stack
- Python 3.12+
- PySide6 / Qt 6
- NumPy
- OpenCV
- scikit-image
- SciPy
- Pillow
- imageio
- ONNX Runtime (اختياري)
- PyTorch (اختياري للبحث والتدريب)
- pytest وpytest-benchmark
- PyInstaller أو Nuitka

## 2. الطبقات
```text
Presentation
    ↓
Application
    ↓
Domain
    ↓
Processing
    ↓
Infrastructure
```

والاعتماد المفضل:
```text
Presentation → Application → Domain
                             ↑
                       Infrastructure
```

يمكن للـ Application استعمال abstraction من Domain للوصول إلى الخدمات، بينما لا ينبغي للـ Domain أن يعتمد مباشرة على PySide6.

## 3. Presentation
مسؤولة عن:
- MainWindow
- Dock widgets
- Canvas
- Toolbars
- dialogs
- parameter controls
- visual feedback
- keyboard/mouse events

ولا تحتوي على خوارزميات DIP.

## 4. Application
مسؤولة عن:
- commands
- use cases
- orchestration
- undo/redo
- tool activation
- import/export workflows
- jobs
- selection of processors

## 5. Domain
يمثل المفاهيم الأساسية:
- Project
- Document
- Layer
- Selection
- Mask
- Object
- Transform
- Operation
- Metadata

ويجب أن يبقى مستقلاً قدر الإمكان عن تفاصيل المكتبات.

## 6. Processing
يوفر عقوداً موحدة للخوارزميات:
```text
Processor
 ├── validate()
 ├── preview()
 └── process()
```

ويحتوي التصنيفات الأكاديمية للمعالجة.

## 7. Infrastructure
تتعامل مع:
- filesystem
- image codecs
- project persistence
- cache
- database/index إن لزم
- external ML runtimes

## 8. لماذا PySide6؟
لأنه يوفر نموذج Desktop ناضجاً مع Qt Docking، menus، actions، shortcuts، dialogs، painting، threading/signals، وإمكانية بناء Workspace قابلة للتخصيص.

## 9. مبدأ فصل المكتبات
OpenCV وscikit-image وSciPy ليست هي architecture. هي backends تنفيذية. يمكن أن يوجد:
```text
GaussianBlurProcessor
        ↓
Processing Backend
 ├── NumPy
 ├── SciPy
 └── OpenCV
```

وبذلك لا يصبح المشروع مرتبطاً بخوارزمية أو مكتبة واحدة.
