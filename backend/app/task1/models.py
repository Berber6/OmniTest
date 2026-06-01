"""Pydantic models for Task1 (crawl, feature extraction, scenario generation)."""

from typing import Optional

from pydantic import BaseModel, Field


class DocumentChunk(BaseModel):
    """A chunk of parsed document content with metadata."""

    id: str = Field(..., description="Unique chunk identifier")
    content: str = Field(..., description="Chunk text content")
    source_url: str = Field(..., description="Source document URL")
    title: str = Field(default="", description="Source page title")
    metadata: dict = Field(default_factory=dict, description="Additional metadata")


class CrawledPage(BaseModel):
    """A crawled web page with its content and metadata."""

    url: str = Field(..., description="Page URL")
    title: str = Field(default="", description="Page title")
    content: str = Field(..., description="Page content as markdown")
    metadata: dict = Field(default_factory=dict, description="Crawl metadata")
    images: list[dict] = Field(
        default_factory=list,
        description="Downloaded images: [{'url': '...', 'alt': '...', 'local_path': '...'}]",
    )


class Step(BaseModel):
    """A single step in a test scenario."""

    step: int = Field(..., description="Step number, starting from 1")
    action: str = Field(..., description="Action to perform, e.g. 'click', 'type', 'navigate'")
    target: str = Field(..., description="CSS selector or description of the target element")
    source_chunk_id: Optional[str] = Field(
        None, description="ID of the source chunk that this step was derived from"
    )


class Expectation(BaseModel):
    """An expected outcome to verify after executing a scenario."""

    type: str = Field(
        ...,
        description="Type of expectation: 'page_content', 'url_change', 'element_exists', 'visual_match', 'element_visible', 'toast_message'",
    )
    description: str = Field(..., description="Human-readable description of what should be true")
    source_chunk_id: Optional[str] = Field(
        None, description="ID of the source chunk that this expectation was derived from"
    )
    reference_image: Optional[str] = Field(
        None, description="Local path to reference image for visual_match expectations"
    )


class Feature(BaseModel):
    """A feature extracted from crawled web content."""

    id: str = Field(..., description="Unique identifier for the feature")
    name: str = Field(..., description="Short name of the feature")
    category: str = Field(..., description="Category, e.g. 'navigation', 'form', 'display'")
    description: str = Field(..., description="Detailed description of the feature")
    source_chunks: list[str] = Field(
        default_factory=list, description="IDs of source chunks that informed this feature"
    )


class TestScenario(BaseModel):
    """A test scenario derived from a feature."""

    id: str = Field(..., description="Unique identifier for the scenario")
    feature_id: str = Field(..., description="ID of the parent feature")
    name: str = Field(..., description="Short name of the scenario")
    steps: list[Step] = Field(
        default_factory=list, description="Ordered list of steps to execute"
    )
    expectations: list[Expectation] = Field(
        default_factory=list, description="Expected outcomes to verify"
    )


class GranularityIssue(BaseModel):
    """A granularity validation issue for a feature."""

    feature_id: str = Field(..., description="Feature ID with the issue")
    issue_type: str = Field(
        ...,
        description="Type: too_fine, too_coarse, step_count_out_of_range, missing_expectations",
    )
    description: str = Field(..., description="Human-readable issue description")
    suggestion: str = Field(default="", description="Suggested fix")


class GranularityReport(BaseModel):
    """Report from granularity validation."""

    valid: bool = Field(..., description="Whether all features pass granularity checks")
    issues: list[GranularityIssue] = Field(
        default_factory=list, description="List of granularity issues found"
    )
    features_needing_re_extraction: list[str] = Field(
        default_factory=list, description="Feature IDs that should be re-extracted"
    )


# --- Request / Response models for API endpoints ---

class CrawlRequest(BaseModel):
    """Request body for starting a crawl."""

    url: str = Field(..., description="Target URL to crawl")
    depth: int = Field(default=1, description="Crawl depth for multi-page sites")


class CrawlResponse(BaseModel):
    """Response after a crawl completes."""

    status: str = Field(..., description="Status of the crawl: 'success' or 'error'")
    pages_crawled: int = Field(default=0, description="Number of pages successfully crawled")
    chunks_stored: int = Field(default=0, description="Number of text chunks stored in ChromaDB")
    message: str = Field(default="", description="Additional info or error message")


class ExtractFeaturesResponse(BaseModel):
    """Response after feature extraction completes."""

    status: str = Field(..., description="Status: 'success' or 'error'")
    features_count: int = Field(default=0, description="Number of features extracted")
    message: str = Field(default="", description="Additional info or error message")


class GenerateScenariosRequest(BaseModel):
    """Request body for generating scenarios from features."""

    feature_ids: Optional[list[str]] = Field(
        None, description="Optional list of feature IDs; if omitted, all features are used"
    )


class GenerateScenariosResponse(BaseModel):
    """Response after scenario generation completes."""

    status: str = Field(..., description="Status: 'success' or 'error'")
    scenarios_count: int = Field(default=0, description="Number of scenarios generated")
    message: str = Field(default="", description="Additional info or error message")