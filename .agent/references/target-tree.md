# Target Source Tree

```text
src/dip_studio/
├── domain/          # pure model and policies
├── application/     # commands, use cases, ports
├── infrastructure/  # filesystem, codecs, NumPy/OpenCV adapters
├── rendering/       # document-to-pixels; separate from processing
├── presentation/    # PySide6 views and composition
└── shared/          # tokens and narrow cross-cutting primitives
```

لا تنشئ مجلدًا قبل وجود use case أو boundary يبرره. المكوّن القابل لإعادة الاستخدام يعيش في أضيق طبقة تملك سلوكه.
