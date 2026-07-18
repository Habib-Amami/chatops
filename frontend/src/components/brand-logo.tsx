import Image from "next/image";

import { cn } from "@/lib/utils";

type BrandLogoProps = {
  className?: string;
  priority?: boolean;
};

export function BrandLogo({ className, priority = false }: BrandLogoProps) {
  return (
    <Image
      src="/brand/talan-logo.svg"
      alt="Talan"
      width={1160}
      height={281}
      className={cn("h-8 w-auto object-contain", className)}
      priority={priority}
    />
  );
}
