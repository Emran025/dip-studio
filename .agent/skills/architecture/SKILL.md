---
name: dip-studio-architecture
description: Govern DIP Studio clean architecture, dependency direction, and reusable module boundaries. Use before adding or moving domain, application, infrastructure, rendering, or PySide6 code.
---

# Architecture Contract

- أبقِ `domain` خالصًا من PySide6 وNumPy وfilesystem؛ يحتوي entities/value objects/policies.
- أبقِ `application` على use cases وports؛ لا Qt ولا تفاصيل تخزين.
- اجعل `infrastructure` مكان adapters للملفات والصيغ والمكتبات الخارجية.
- اجعل `presentation` طبقة تركيب وعرض فقط؛ لا تنفذ algorithm أو تملك document state.
- اجعل `shared` للتوكنات والم primitives المشتركة، لا مستودعًا لمنطق عشوائي.
- وجّه الاعتماد إلى الداخل: presentation → application → domain، وinfrastructure → application/domain.
- أضف interface قبل adapter، واختبر use case دون GUI.
- لا تضف مكتبة أو طبقة جديدة قبل توثيق سببها وإصدارها ورخصتها في `docs/architecture/dependencies.md`.
- لا تنفذ إعادة كتابة شاملة؛ كل نقل ملف يجب أن يملك اختبارًا أو سببًا موثقًا.
