# 08 — Tools, Commands, Parameters and History

## 1. Tool Definition
```text
Tool
 ├── id
 ├── name
 ├── icon
 ├── category
 ├── description
 ├── shortcut
 ├── parameter_schema
 ├── interaction
 ├── processor
 └── capabilities
```

## 2. ToolRegistry
مسؤوليته:
- register
- unregister
- get
- find
- list
- group
- discover

وبالتالي تصبح الأدوات قابلة للاكتشاف دون ربطها مباشرة بـ MainWindow.

## 3. Parameter Schema
```text
Parameter
 ├── id
 ├── type
 ├── label
 ├── default
 ├── minimum
 ├── maximum
 ├── step
 ├── choices
 ├── description
 └── validation
```

## 4. Command
```text
Command
 ├── execute()
 ├── undo()
 ├── redo()
 └── metadata
```

أمثلة:
```text
File.Open
File.Save
Edit.Undo
Edit.Redo
Layer.New
Layer.Delete
Layer.Duplicate
Selection.Invert
Filter.GaussianBlur
Filter.Canny
```

## 5. Preview / Apply / Cancel
عند تعديل Filter:
```text
Edit Parameters
      ↓
Temporary Preview
      ├── Apply → Commit Command
      └── Cancel → Discard Temporary State
```

لا يجب أن يسجل كل تغيير Slider كعنصر History مستقل.

## 6. History
History يمثل Commands أو state transitions.

مثال:
```text
1. Add Image
2. Create Layer
3. Gaussian Blur
4. Adjust Brightness
5. Create Mask
```

Undo وRedo يعيدان تنفيذ أو عكس هذه العمليات بدلاً من الاحتفاظ بنسخة كاملة من الصورة بعد كل خطوة.

## 7. التفاعل الموحد
Menu وToolbar وMouse وKeyboard وCommand Palette يجب أن تصل كلها إلى نفس Command Handler.

```text
User Input
   ↓
Command
   ↓
Application Service
   ↓
Domain Change / Processing Job
   ↓
History
```
