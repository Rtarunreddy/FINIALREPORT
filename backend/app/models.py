"""Validated settings shared by the API and formatter."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Page(Settings):
    size: Literal["Existing report", "A4", "Letter"] = "Existing report"
    top: float = Field(default=1, ge=0.2, le=3)
    bottom: float = Field(default=1, ge=0.2, le=3)
    left: float = Field(default=1.25, ge=0.2, le=3)
    right: float = Field(default=1, ge=0.2, le=3)
    columns: int = Field(default=0, ge=0, le=2)
    border: Literal["none", "box", "double"] = "none"


class Text(Settings):
    font: str = Field(default="Times New Roman", min_length=1, max_length=80)
    size: float = Field(default=12, ge=8, le=48)
    alignment: Literal["left", "center", "right", "justify"] = "justify"
    lineSpacing: float = Field(default=1.5, ge=1, le=3)
    before: float = Field(default=0, ge=0, le=72)
    after: float = Field(default=6, ge=0, le=72)
    firstLineIndent: float = Field(default=0, ge=0, le=2)


class Heading(Text):
    alignment: Literal["left", "center", "right", "justify"] = "left"
    bold: bool = True
    lineSpacing: float = Field(default=1.15, ge=1, le=3)


class Headings(Settings):
    h1: Heading = Field(default_factory=lambda: Heading(size=16, before=18, after=10))
    h2: Heading = Field(default_factory=lambda: Heading(size=14, before=14, after=8))
    h3: Heading = Field(default_factory=lambda: Heading(size=12, before=10, after=6))


class Extras(Settings):
    headerText: str = Field(default="", max_length=240)
    footerText: str = Field(default="", max_length=240)
    pageNumbers: bool = False
    pageNumberPosition: Literal["header", "footer"] = "footer"
    imageMaxWidth: float = Field(default=0, ge=0, le=20)
    startChaptersOnNewPage: bool = False
    normalizeTables: bool = True
    normalizeCaptions: bool = True
    normalizeHeadersFooters: bool = True
    centerImages: bool = True
    fitImages: bool = True
    resetBodyIndents: bool = True


class Profile(Settings):
    id: str | None = Field(default=None, max_length=80)
    name: str = Field(min_length=1, max_length=80)
    page: Page = Field(default_factory=Page)
    body: Text = Field(default_factory=Text)
    headings: Headings = Field(default_factory=Headings)
    extras: Extras = Field(default_factory=Extras)

    @model_validator(mode="after")
    def meaningful_names(self):
        if not self.name.strip() or not all(x.font.strip() for x in [self.body, self.headings.h1, self.headings.h2, self.headings.h3]):
            raise ValueError("Template name and font cannot be blank.")
        return self


class ApplyRequest(Settings):
    teamId: str | None = None
    profile: Profile | None = None            # omit both fields for the one-click default
    templateId: str | None = Field(default=None, max_length=80)


class Review(Settings):
    rating: int = Field(ge=1, le=5)
    comment: str = Field(default="", max_length=1000)
