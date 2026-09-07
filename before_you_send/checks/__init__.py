"""The checks, in the order a reader should meet them.

Two kinds. Page checks look at what was painted on one page and need the drawing
instructions. Document checks look at the file as a whole and need only the object
graph. Keeping them apart means a page that cannot be interpreted costs the report
its page checks and nothing else.
"""

from __future__ import annotations

from before_you_send.checks.history import earlier_versions_retained
from before_you_send.checks.metadata import (
    annotation_authors,
    build_path_in_metadata,
    descriptive_metadata,
    document_author,
    xmp_metadata,
)
from before_you_send.checks.payload import active_content, embedded_files, form_field_values
from before_you_send.checks.protection import (
    encryption_without_a_password,
    hidden_layers,
    unapplied_redaction_marks,
)
from before_you_send.checks.visibility import (
    covered_text,
    image_over_text,
    invisible_text,
    text_matching_background,
    text_outside_page,
)

PAGE_CHECKS = (
    covered_text,
    invisible_text,
    text_matching_background,
    text_outside_page,
    image_over_text,
)

DOCUMENT_CHECKS = (
    unapplied_redaction_marks,
    embedded_files,
    active_content,
    form_field_values,
    earlier_versions_retained,
    hidden_layers,
    annotation_authors,
    document_author,
    xmp_metadata,
    build_path_in_metadata,
    descriptive_metadata,
    encryption_without_a_password,
)

__all__ = ["PAGE_CHECKS", "DOCUMENT_CHECKS"]
