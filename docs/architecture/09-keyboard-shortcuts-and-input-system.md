# 09 — Keyboard Shortcuts and Input System

## 1. الهدف
نظام الاختصارات ليس مجموعة if statements داخل Widgets. يجب أن يكون subsystem مستقلاً، سياقياً وقابلاً للتخصيص.

## 2. Pipeline
```text
Keyboard Input
     ↓
Input Dispatcher
     ↓
Focus Resolver
     ↓
Context Resolver
     ↓
Shortcut Resolver
     ↓
Command Registry
     ↓
Command Handler
```

## 3. Shortcut Definition
```text
Shortcut
 ├── command_id
 ├── key
 ├── modifiers
 ├── context
 ├── priority
 ├── enabled
 └── user_customizable
```

## 4. Contexts
- Global
- Application
- Canvas
- Tool
- Layer Panel
- History Panel
- Properties Panel
- Timeline
- Text Editing
- Dialog
- Input Field
- Selection
- Tracking

## 5. Priority
```text
Text Input
   ↓
Modal Dialog
   ↓
Focused Panel
   ↓
Canvas / Tool
   ↓
Application
   ↓
Global
```

وهذا يمنع مثلاً اختصاراً عاماً من اعتراض حرف يكتبه المستخدم داخل Text Input.

## 6. Default Shortcuts
```text
V Move
M Selection
L Lasso
C Crop
B Brush
E Eraser
G Gradient
H Hand
Z Zoom
I Eyedropper
T Text
U Shape
```

يمكن استخدام B وShift+B للتنقل داخل مجموعة الأدوات.

Space أثناء السحب يمكن أن يعمل كـ temporary Hand/Pan.

## 7. Canvas Shortcuts
- Space + drag → pan
- Ctrl + wheel → zoom
- modifiers → constrain/alternate behavior

## 8. Shortcut Editor
يجب أن يوفر:
- search
- command name
- current shortcut
- record shortcut
- conflict detection
- replace
- assign another
- cancel

## 9. Profiles
- DIP Studio Default
- Photoshop-like
- DIP Laboratory
- Custom

## 10. Dynamic Registration
عند إضافة Plugin Tool جديدة يجب أن تظهر تلقائياً في Shortcut Editor إذا أعلنت عن shortcut قابل للتخصيص.
