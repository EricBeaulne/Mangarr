import clsx from 'clsx';
import type { Series } from '../../types';

interface BadgeProps {
  children: React.ReactNode;
  variant?: 'default' | 'success' | 'warning' | 'danger' | 'info' | 'muted';
  size?: 'sm' | 'md';
  className?: string;
}

const variantClasses: Record<NonNullable<BadgeProps['variant']>, string> = {
  default: 'bg-mangarr-input text-mangarr-text border-mangarr-border',
  success: 'bg-mangarr-success/90 text-white border-mangarr-success',
  warning: 'bg-mangarr-warning/90 text-black border-mangarr-warning',
  danger: 'bg-mangarr-danger/90 text-white border-mangarr-danger',
  info: 'bg-mangarr-accent/90 text-white border-mangarr-accent',
  muted: 'bg-mangarr-card/90 text-mangarr-text border-mangarr-border',
};

const sizeClasses: Record<NonNullable<BadgeProps['size']>, string> = {
  sm: 'px-1.5 py-0.5 text-xs',
  md: 'px-2.5 py-1 text-xs',
};

export function Badge({ children, variant = 'default', size = 'md', className }: BadgeProps) {
  return (
    <span
      className={clsx(
        'inline-flex items-center font-medium rounded border',
        variantClasses[variant],
        sizeClasses[size],
        className,
      )}
    >
      {children}
    </span>
  );
}

type SeriesStatus = NonNullable<Series['status']>;

const statusVariantMap: Record<SeriesStatus, BadgeProps['variant']> = {
  ongoing: 'info',
  completed: 'success',
  hiatus: 'warning',
  cancelled: 'danger',
};

const statusLabelMap: Record<SeriesStatus, string> = {
  ongoing: 'Ongoing',
  completed: 'Completed',
  hiatus: 'Hiatus',
  cancelled: 'Cancelled',
};

interface StatusBadgeProps {
  status: Series['status'];
  size?: BadgeProps['size'];
  className?: string;
}

export function StatusBadge({ status, size, className }: StatusBadgeProps) {
  if (!status) return null;
  return (
    <Badge variant={statusVariantMap[status]} size={size} className={className}>
      {statusLabelMap[status]}
    </Badge>
  );
}

interface ContentRatingBadgeProps {
  rating: string | null | undefined;
  size?: BadgeProps['size'];
  className?: string;
}

const ratingVariantMap: Record<string, BadgeProps['variant']> = {
  safe: 'success',
  suggestive: 'warning',
  erotica: 'danger',
  pornographic: 'danger',
};

export function ContentRatingBadge({ rating, size, className }: ContentRatingBadgeProps) {
  if (!rating) return null;
  const variant = ratingVariantMap[rating.toLowerCase()] ?? 'muted';
  return (
    <Badge variant={variant} size={size} className={className}>
      {rating.charAt(0).toUpperCase() + rating.slice(1)}
    </Badge>
  );
}
