"use client";

import { useRouter } from "next/navigation";
import { useCallback } from "react";
import UploadCard from "@/components/UploadCard";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";

/**
 * Upload page — /upload
 * Editorial wrapper for the UploadCard component.
 * Flow: Home (/) → Upload (/upload) → Dashboard (/migration/[id])
 */
export default function UploadPage() {
  const router = useRouter();

  const handleSuccess = useCallback(
    (migrationId: string) => {
      router.push(`/migration/${migrationId}`);
    },
    [router]
  );

  return (
    <div className="flex flex-1 flex-col px-8 pb-24 pt-16 lg:px-16">
      <div className="mx-auto w-full max-w-[1600px]">

        {/* Breadcrumb */}
        <Link
          href="/"
          className="group mb-12 inline-flex items-center gap-2 text-[10px] font-medium tracking-[0.25em] uppercase text-themeTextMuted transition-colors duration-500 hover:text-themeText"
        >
          <ArrowLeft className="h-3 w-3 transition-transform duration-500 group-hover:-translate-x-1" aria-hidden="true" />
          Back to Home
        </Link>

        {/* Editorial page header — asymmetric layout */}
        <div className="mb-16 border-b border-themeBorder pb-10">
          <div className="flex items-center gap-3 mb-4">
            <div className="h-px w-8 bg-themeText/30" aria-hidden="true" />
            <span className="overline">Step 01 of 03</span>
          </div>
          <h1
            className="font-serif text-4xl font-normal text-themeText lg:text-6xl"
            style={{ fontFamily: "'Playfair Display', Georgia, serif" }}
          >
            Upload Your{" "}
            <em style={{ color: "#D4AF37" }}>CUDA Project</em>
          </h1>
          <p className="mt-4 max-w-lg text-base leading-relaxed text-themeTextMuted">
            Provide a single <code className="font-mono text-sm text-themeText">.cu</code> file
            or a <code className="font-mono text-sm text-themeText">.zip</code> archive,
            configure your target GPU, and begin the migration.
          </p>
        </div>

        {/* Upload card — centered in the editorial grid */}
        <div className="flex justify-center">
          <UploadCard onSuccess={handleSuccess} />
        </div>
      </div>
    </div>
  );
}
