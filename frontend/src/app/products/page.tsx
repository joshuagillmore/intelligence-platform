'use client';

import { ProductsView } from '@/components/sentinel/views/ProductsView';
import { MProducts, MobileSwap } from '@/components/sentinel/MobileViews';

export default function ProductsPage() {
  return <MobileSwap desktop={<ProductsView />} mobile={<MProducts />} />;
}
