from __future__ import annotations

import argparse
import sys

from sqlalchemy import select

from app.core.secrets import SecretCryptoError, decrypt_secret, encrypt_secret, mask_api_key
from app.db.session import SessionLocal
from app.models.llm_profile import LLMProfile


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Migrate llm_profiles.api_key_ciphertext to enc: (portable encryption).")
    parser.add_argument("--dry-run", action="store_true", help="Decrypt and compute new ciphertext, but do not write to DB.")
    args = parser.parse_args(argv)

    migrated = 0
    skipped = 0
    failed = 0

    db = SessionLocal()
    try:
        rows = db.execute(select(LLMProfile).order_by(LLMProfile.updated_at.desc())).scalars().all()
        for row in rows:
            ct = (row.api_key_ciphertext or "").strip()
            if not ct:
                skipped += 1
                continue
            if ct.startswith("enc:"):
                skipped += 1
                continue

            try:
                plaintext = decrypt_secret(ct).strip()
            except SecretCryptoError as exc:
                failed += 1
                print(f"[FAIL] profile_id={row.id} reason=decrypt_failed error={type(exc).__name__}")
                continue

            if not plaintext:
                skipped += 1
                continue

            try:
                new_ct = encrypt_secret(plaintext)
            except SecretCryptoError as exc:
                print(f"[FATAL] encryption_not_configured error={type(exc).__name__}: {exc}")
                return 2

            if not new_ct.startswith("enc:"):
                print("[FATAL] encrypt_secret did not produce enc:. Set SECRET_ENCRYPTION_KEY and retry.")
                return 2

            row.api_key_ciphertext = new_ct
            row.api_key_masked = mask_api_key(plaintext)
            migrated += 1

        if args.dry_run:
            db.rollback()
            print(f"[DRY-RUN] migrated={migrated} skipped={skipped} failed={failed}")
            return 0 if failed == 0 else 1

        db.commit()
        print(f"[OK] migrated={migrated} skipped={skipped} failed={failed}")
        return 0 if failed == 0 else 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
