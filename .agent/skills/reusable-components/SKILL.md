---
name: dip-studio-reusable-components
description: Enforce reuse-first and theme-first decisions for every DIP Studio widget, token, command, service, or processing component.
---

# Reuse Gate

قبل كتابة أي مكوّن: ابحث في `src/dip_studio`, ثم افحص `presentation/theme.py` والوثائق. اختر بالترتيب: reuse مباشر، توسيع configurable، استخراج abstraction، ثم new.

- لا تنسخ widget بسبب فرق لون/spacing؛ استخدم ThemeTokens أو parameter.
- لا تنشئ ThemeData أو palette داخل view.
- لا تجعل widget يملك business state؛ مرّر view model أو command.
- أنشئ مكوّنًا جديدًا فقط مع owner واضح، contract، test، واستخدام/سبب مستقل.
- عند اختيار `new` املأ `references/component-decision-record.md`.
- افصل processing عن rendering؛ algorithm يعيد بيانات، وrenderer يعرضها.
