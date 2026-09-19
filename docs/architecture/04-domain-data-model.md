# 04 — Domain Data Model

## 1. Project
```text
Project
 ├── Documents
 ├── Assets
 ├── Workspace
 └── Metadata
```

## 2. Document
```text
Document
 ├── dimensions
 ├── resolution
 ├── color_space
 ├── LayerTree
 ├── Selections
 ├── Objects
 ├── Guides
 ├── Operations
 └── Metadata
```

## 3. ImageData
`numpy.ndarray` ليس نموذج الصورة كاملاً. هو pixel buffer فقط.

```text
ImageData
 ├── id
 ├── width
 ├── height
 ├── channels
 ├── dtype
 ├── color_space
 ├── alpha_mode
 ├── metadata
 └── data_reference
```

## 4. Layer
```text
Layer
 ├── id
 ├── name
 ├── type
 ├── visible
 ├── locked
 ├── opacity
 ├── blend_mode
 ├── transform
 ├── mask_reference
 └── content_reference
```

## 5. Layer Types
- ImageLayer
- AdjustmentLayer
- FilterLayer
- TextLayer
- ShapeLayer
- GroupLayer

## 6. Transform
```text
position
scale
rotation
skew
flip
origin
```

ويمكن تمثيله داخلياً بمصفوفة homogeneous 3×3.

## 7. Operations
المعالجة غير التدميرية تمثل كعمليات، مثلاً:
```text
Original
  ↓
Brightness(+20)
  ↓
Contrast(+10)
  ↓
GaussianBlur(sigma=2)
  ↓
Sharpen
```

وقد تتحول لاحقاً إلى DAG:
```text
Original
 ├── Blur ─────┐
 │             ├── Composite
 └── Edge ─────┘
```

## 8. Object Model
```text
Object
 ├── id
 ├── class_name
 ├── confidence
 ├── bounding_box
 ├── centroid
 ├── contour
 ├── mask_reference
 ├── area
 ├── perimeter
 ├── orientation
 ├── features
 └── metadata
```

## 9. Feature Separation
### Geometry
area, perimeter, centroid, bounding box

### Shape
circularity, solidity, extent, aspect ratio

### Appearance
mean color, histogram, texture

### ML
embedding

هذا يسمح بربط النظام بمراحل DIP: representation → description → recognition.
