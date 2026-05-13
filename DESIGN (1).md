---
name: OjaPass Identity System
colors:
  surface: '#fcf9f3'
  surface-dim: '#dcdad4'
  surface-bright: '#fcf9f3'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#f6f3ed'
  surface-container: '#f0eee8'
  surface-container-high: '#ebe8e2'
  surface-container-highest: '#e5e2dc'
  on-surface: '#1c1c18'
  on-surface-variant: '#3f4942'
  inverse-surface: '#31312d'
  inverse-on-surface: '#f3f0ea'
  outline: '#6f7a71'
  outline-variant: '#bfc9bf'
  surface-tint: '#1b6b45'
  primary: '#005231'
  on-primary: '#ffffff'
  primary-container: '#1b6b45'
  on-primary-container: '#9be9b9'
  inverse-primary: '#8ad7a8'
  secondary: '#805600'
  on-secondary: '#ffffff'
  secondary-container: '#ffb21d'
  on-secondary-container: '#6b4800'
  tertiary: '#1d5035'
  on-tertiary: '#ffffff'
  tertiary-container: '#36684b'
  on-tertiary-container: '#afe4c1'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#a5f3c3'
  primary-fixed-dim: '#8ad7a8'
  on-primary-fixed: '#002111'
  on-primary-fixed-variant: '#005231'
  secondary-fixed: '#ffddaf'
  secondary-fixed-dim: '#ffba44'
  on-secondary-fixed: '#281800'
  on-secondary-fixed-variant: '#614000'
  tertiary-fixed: '#b9efcb'
  tertiary-fixed-dim: '#9dd3b0'
  on-tertiary-fixed: '#002111'
  on-tertiary-fixed-variant: '#1d5035'
  background: '#fcf9f3'
  on-background: '#1c1c18'
  surface-variant: '#e5e2dc'
typography:
  display-lg:
    fontFamily: Fraunces
    fontSize: 48px
    fontWeight: '700'
    lineHeight: 56px
    letterSpacing: -0.02em
  display-md:
    fontFamily: Fraunces
    fontSize: 36px
    fontWeight: '600'
    lineHeight: 44px
    letterSpacing: -0.01em
  headline-lg:
    fontFamily: Fraunces
    fontSize: 28px
    fontWeight: '600'
    lineHeight: 36px
  headline-md:
    fontFamily: dmSans
    fontSize: 20px
    fontWeight: '700'
    lineHeight: 28px
  body-lg:
    fontFamily: dmSans
    fontSize: 18px
    fontWeight: '400'
    lineHeight: 28px
  body-md:
    fontFamily: dmSans
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
  label-lg:
    fontFamily: dmSans
    fontSize: 14px
    fontWeight: '700'
    lineHeight: 20px
    letterSpacing: 0.01em
  label-sm:
    fontFamily: dmSans
    fontSize: 12px
    fontWeight: '500'
    lineHeight: 16px
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  base: 4px
  xs: 4px
  sm: 8px
  md: 16px
  lg: 24px
  xl: 32px
  gutter: 16px
  margin-mobile: 20px
  margin-desktop: 64px
---

## Brand & Style

The design system is built on the concept of "The Modern Marketplace"—a bridge between traditional Nigerian commerce and digital financial empowerment. The personality is **Grounded and Institutional**, yet **Warm and Human**. It avoids the clinical coldness of global fintech by utilizing earthy, organic tones that resonate with the local environment while maintaining a sharp, professional execution that signals reliability.

The aesthetic follows a **Modern Corporate** direction with **Tactile accents**. It leverages high-quality typography and a sophisticated color palette to create an environment where a small business owner feels both respected and protected. The visual language is structured and orderly (to build trust) but uses soft lighting and warm neutrals to remain accessible.

## Colors

The palette is anchored by **Oja Green**, a deep forest hue that symbolizes growth and the traditional "green-white-green" heritage without being literal. 

- **Primary (Oja Green):** Used for primary actions, headers, and brand-defining moments. It represents the "Pass" or the gateway to formal finance.
- **Accent (Gold Market):** Used sparingly for success states, highlights, and "wealth creation" indicators. It provides a warm, energetic contrast to the deep green.
- **Surface (Warm Smoke):** The light-mode foundation. It is an off-white that reduces eye strain in bright sunlight and feels more "natural" than pure white.
- **Surface (Charcoal Deep):** For dark-mode applications, this deep green-black provides a premium, secure feel.
- **Muted Sage:** Used for secondary containers, inactive states, and backgrounds for supplementary info cards.

## Typography

This design system uses a dual-type approach to balance character with utility.

- **Fraunces** is the "soul" of the brand. Use it for large displays, onboarding headers, and currency amounts. Its variable soft-edges and "Wonky" alternates (used subtly) provide a human, crafted feel that differentiates it from generic tech brands.
- **DM Sans** is the "engine." It handles all functional data, forms, and body text. Its geometric clarity ensures readability across various mobile device qualities common in the informal economy.

**Weight Usage:** Bold weights in DM Sans should be reserved for high-priority labels. Fraunces should generally be used in Semi-Bold or Bold to maximize its unique serif characteristics.

## Layout & Spacing

The layout utilizes a **12-column fluid grid** for desktop and a **4-column fluid grid** for mobile. 

A strict **8px soft-grid** governs all internal spacing. The "Warm Smoke" background should be treated as a canvas; components should be grouped into logical "market stalls" (cards) with generous 24px margins between them to avoid visual clutter. In mobile views, prioritize vertical stacking with a minimum touch target area of 48px for all interactive elements.

## Elevation & Depth

This design system avoids harsh, artificial shadows in favor of **Tonal Layers** and **Soft Ambient Occlusion**.

1.  **Level 0 (Base):** Warm Smoke background.
2.  **Level 1 (Cards/Containers):** Pure white surfaces with a very subtle 1px border in `Muted Sage` at 20% opacity. 
3.  **Level 2 (Active Elements):** For modals or floating action buttons, use a "Warm Shadow"—a soft, diffused shadow (Blur: 20px, Y: 8px) tinted with a hint of Oja Green (#1B6B45) at 8% opacity. This makes the elevation feel integrated with the brand palette rather than a generic grey.

Depth is also communicated through the use of **Gold Market** accents as an "underline" or high-light strip on the top of important cards, signaling priority without needing heavy shadows.

## Shapes

The shape language is **Rounded**, reflecting a friendly and approachable nature. 

- **Primary Buttons/Cards:** 0.5rem (8px) radius. This provides a modern look that feels sturdy but not sharp.
- **Search Inputs/Tags:** 1rem (16px) radius to distinguish them from structural layout blocks.
- **Icon Enclosures:** Circular containers for decorative icons, but square with 4px radius for functional system icons.

Interactive elements should have a slight "squishy" feel during the active state (press), briefly increasing the perceived internal padding to reinforce the tactile nature of the UI.

## Components

- **Buttons:** Primary buttons use Oja Green with White text. Secondary buttons use a Muted Sage ghost style (outline). Success actions use Gold Market background with Ink text for maximum contrast.
- **Input Fields:** Use a solid White background with a 1px border in Muted Sage. On focus, the border thickens to 2px and changes to Oja Green. Labels always sit above the field in `label-lg` style.
- **Cards:** Cards are the primary unit of the UI. They should have a 1px soft border. For "Business Growth" metrics, use a Gold Market top-border (4px thick) to celebrate the user's success.
- **Chips/Badges:** Use "Pill" shapes. Success badges: Light Sage background with Oja Green text. Pending badges: Pale Gold background with Ink text.
- **Business Identity Card:** A specialized component mimicking a physical ID. It uses a gradient of Oja Green, featuring the user's "Identity Score" in Fraunces.
- **Lists:** Transaction lists should be high-contrast. Amounts should be in `headline-md` (DM Sans Bold) to ensure the primary data point is instantly recognizable.
- **Progress Bars:** Use a thick (8px) track in Muted Sage (20% opacity) with the progress indicator in Gold Market to represent the harvest/growth of the business.