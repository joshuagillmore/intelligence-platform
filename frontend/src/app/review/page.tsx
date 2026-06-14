'use client';

import { ReviewView } from '@/components/sentinel/views/ReviewView';
import { MReview, MobileSwap } from '@/components/sentinel/MobileViews';

export default function ReviewPage() {
  return <MobileSwap desktop={<ReviewView />} mobile={<MReview />} />;
}
