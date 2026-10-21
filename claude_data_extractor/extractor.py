"""
Claude Data Extractor

Module for extracting Kondo physics data from PDF files with the Claude API.
"""

import json
import os
from pathlib import Path
from typing import Optional, Dict, List, Any

import pandas as pd
from dotenv import load_dotenv
from anthropic import Anthropic

from nanosynthra.modules.data_extractor import read_pdf_text_with_metadata
from .schema import KONDO_SCHEMA

# Load environment variables from .env file
load_dotenv()


class ClaudeDataExtractor:
    """Extracts Kondo physics data from PDF files with the Claude API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: str = "claude-sonnet-4-20250514"
    ):
        """
        Initialize the ClaudeDataExtractor.

        Args:
            api_key: Anthropic API key (read from the ANTHROPIC_API_KEY env var if None)
            model_name: Claude model name to use (default: claude-sonnet-4-20250514)
        """
        # Take the API key from the argument or the environment
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError(
                "API key required. Pass api_key or set the ANTHROPIC_API_KEY environment variable."
            )

        self.model_name = model_name
        self.client = Anthropic(api_key=self.api_key)

    def extract_kondo_data_from_pdf(
        self,
        pdf_file: str,
        output_excel: str,
        max_chars: int = 200000
    ) -> Dict[str, Any]:
        """
        Extract Kondo physics data from a PDF file into the structured schema.

        Args:
            pdf_file: Input PDF file (scientific paper)
            output_excel: Output Excel file
            max_chars: Maximum number of characters sent to Claude (default: 200000)

        Returns:
            Dict: Extraction results
        """
        # Read the PDF
        print(f"Reading PDF file: {pdf_file}")
        pdf_data = read_pdf_text_with_metadata(pdf_file)
        print(f"PDF info: {pdf_data['num_pages']} pages, {len(pdf_data['text'])} characters")

        # Truncate the text (if needed)
        text = pdf_data['text']
        if len(text) > max_chars:
            print(f"WARNING: Text too long ({len(text)} characters), truncating to {max_chars} characters.")
            text = text[:max_chars] + "\n\n... (text truncated)"
        else:
            print(f"Using the full text: {len(text)} characters")

        # Dedicated prompt for Kondo physics research
        kondo_prompt = f"""Extract Kondo physics and DFT calculation data from this scientific paper.

The paper is a study of ZnO nanoribbons, nanoclusters, or similar nanostructures.
It concerns Kondo physics, magnetic properties, and DFT calculations.

IMPORTANT: PLEASE EXAMINE THE ENTIRE PAPER. Do not read only the abstract; READ the Methods, Results, Discussion, Figures, and Tables sections CAREFULLY.

PLEASE EXTRACT THE FOLLOWING FIELDS:

**Basic Information:**
- title: Full title of the paper
- doi: DOI (if available, e.g. "10.1103/PhysRevB.95.075131")
- material: Material studied (e.g. "ZnO nanoribbon")
- impurity: MAGNETIC dopant element (e.g. "Co", "Fe", "Mn", "Ni", "Cr") — magnetic elements ONLY
- passivation_element: PASSIVATION element (e.g. "H", "S", "F", "Cl") — edge/surface passivant

**Geometry:**
- width_nm: Nanoribbon width (nm, numeric)
- edge_type: "zigzag", "armchair", or null
- impurity_position: "edge", "bulk", "center", or null
- distance_to_edge_nm: Distance to the edge (nm, numeric or null)
- nanoribbon_length_nm: Nanoribbon length (nm, numeric or null)
- nanoribbon_width_units: Width unit ("pairs", "nm", "angstrom", "unit_cells", or null)
- co_substitution_site: Co substitution site ("edge", "center", "bulk", "random", or null)
- nanoribbon_W: Ribbon width in unit cells (integer or null)
- nanoribbon_L: Ribbon length in unit cells (integer or null)

**Magnetic Properties:**
- magnetic_moment_uB: Co/impurity magnetic moment (μB, numeric)
- co_local_moment_uB: Co local magnetic moment (μB, numeric or null)
- total_magnetization_uB: Total magnetization (μB, numeric or null)
- magnetic_coupling: "ferromagnetic", "antiferromagnetic", "paramagnetic", or null
- kondo_temperature_K: Kondo temperature (K, numeric or null)
- kondo_temperature_nrg_K: NRG-computed T_K (K, numeric or null)
- kondo_temperature_analytical_K: Analytical (Haldane formula) T_K (K, numeric or null)
- spin_polarization_percent: Spin polarization (%, numeric or null)
- spin_polarization_at_fermi_percent: Spin polarization at E_F (%, numeric or null)
- magnetic_anisotropy: Description of the magnetic anisotropy, or null
- magnetic_anisotropy_energy_meV: Magnetic anisotropy energy (meV, numeric or null)
- easy_axis_direction: Easy-axis direction ("x", "y", "z", "[001]", etc., or null)
- exchange_coupling_J_meV: Co-Co exchange coupling J (meV, may be negative, numeric or null)
- heisenberg_J_meV: Heisenberg model J (meV, numeric or null)

**Electronic Properties:**
- formation_energy_eV: Formation energy (eV, numeric)
- band_gap_eV: Band gap (eV, numeric)
- band_gap_direct_eV: Direct band gap (eV, numeric or null)
- band_gap_indirect_eV: Indirect band gap (eV, numeric or null)
- VBM_eV: Valence Band Maximum (eV, numeric or null)
- CBM_eV: Conduction Band Minimum (eV, numeric or null)
- fermi_energy_eV: Fermi energy (eV, numeric or null)
- total_energy_eV: Total DFT energy (eV, numeric or null)
- dos_at_fermi: Total DOS at the Fermi level (states/eV, numeric or null)
- dos_total_at_fermi: Total DOS at the Fermi level (states/eV, numeric or null)
- dos_co_d_at_fermi: Co d-orbital DOS at E_F (states/eV, numeric or null)

**Co d-Orbital Details:**
- co_d_center_of_mass_eV: Co d-orbital center of mass (eV, relative to the Fermi level, numeric or null)
- co_d_width_eV: Co d-orbital width / hybridization Γ (eV, numeric or null)
- co_d_occupation: Co d-orbital occupation ⟨n_d⟩ (numeric or null)
- co_d_spin_up_occupation: Spin-up d occupation (numeric or null)
- co_d_spin_down_occupation: Spin-down d occupation (numeric or null)

**Anderson Model Parameters:**
- anderson_epsilon_d_eV: ε_d — Co d level relative to the Fermi level (eV, numeric or null)
- anderson_U_eV: U — on-site Coulomb repulsion (eV, numeric or null)
- anderson_Gamma_eV: Γ — hybridization width (eV, numeric or null)
- anderson_V_eV: V — hybridization amplitude (eV, numeric or null)
- anderson_D_eV: D — conduction band half-width (eV, numeric or null)

**NRG Results (if present in the paper):**
- nrg_impurity_entropy_kB: Impurity entropy in units of k_B (numeric or null)
- nrg_specific_heat_coefficient: Sommerfeld coefficient γ (numeric or null)
- nrg_magnetic_susceptibility: χ_imp (numeric or null)
- nrg_wilson_ratio: Wilson ratio R ≈ 2 (numeric or null)
- nrg_kondo_peak_width_meV: Kondo resonance half-width (meV, numeric or null)
- nrg_spectral_weight_at_fermi: Spectral weight A(ω=0) (numeric or null)
- nrg_lambda: Wilson Λ parameter (numeric or null)
- nrg_kept_states: Number of kept states M (integer or null)

**Calculation Details:**
- functional: DFT functional abbreviation ("GGA", "LSDA", "LDA", "PBE", "HSE", etc.)
- dft_code: DFT software ("Quantum-ESPRESSO", "VASP", "SIESTA", "ABINIT", or null)
- dft_functional_family: Full functional family ("GGA-PBE", "LDA", "HSE06", etc., or null)
- hubbard_U_Zn_eV: Zn Hubbard U (eV, numeric or null)
- hubbard_U_O_eV: O Hubbard U (eV, numeric or null)
- hubbard_U_co_eV: Co 3d Hubbard U (eV, numeric or null)
- hubbard_J_co_eV: Co Hund coupling J (eV, numeric or null)
- charge_state: Charge state ("+1", "-1", "0", or null)
- ecutwfc_Ry: Plane-wave cutoff (Ry, numeric or null)
- k_points_grid: k-point grid (e.g. "8 1 1", or null)
- pseudopotential_type: Pseudopotential type ("NC", "PAW", "US", or null)

**Paper Metadata:**
- paper_year: Publication year (integer, e.g. 2023)
- paper_authors: Authors (comma-separated string, e.g. "Zhang X, Wang Y")
- paper_journal: Journal name (e.g. "Physical Review B", "Nano Letters")
- experimental_vs_theoretical: "experimental", "theoretical", "both", or null

IMPORTANT NOTES:
1. For numeric values, give only the number (without units). E.g. "3.37" (without writing eV)
2. If a value is not found or not stated, write null
3. If there are several values, choose the most representative one (usually the main value in the paper's results)
4. "impurity" and "passivation_element" are DIFFERENT:
   - impurity: Magnetic dopant (Co, Fe, Mn, Ni, Cr, etc.)
   - passivation_element: Edge/surface passivant (H, S, F, Cl)
5. Fill in the Anderson parameters (ε_d, Γ, U) only if they are stated explicitly in the paper
6. Fill in the NRG results only if the paper contains an NRG calculation

RETURN IN JSON FORMAT (a single record, all fields):
{{
  "title": "...",
  "doi": "..." or null,
  "material": "...",
  "impurity": "..." or null,
  "passivation_element": "..." or null,
  "width_nm": number or null,
  "edge_type": "..." or null,
  "impurity_position": "..." or null,
  "distance_to_edge_nm": number or null,
  "nanoribbon_length_nm": number or null,
  "nanoribbon_width_units": "..." or null,
  "co_substitution_site": "..." or null,
  "nanoribbon_W": integer or null,
  "nanoribbon_L": integer or null,
  "magnetic_moment_uB": number or null,
  "co_local_moment_uB": number or null,
  "total_magnetization_uB": number or null,
  "magnetic_coupling": "..." or null,
  "kondo_temperature_K": number or null,
  "kondo_temperature_nrg_K": number or null,
  "kondo_temperature_analytical_K": number or null,
  "spin_polarization_percent": number or null,
  "spin_polarization_at_fermi_percent": number or null,
  "magnetic_anisotropy": "..." or null,
  "magnetic_anisotropy_energy_meV": number or null,
  "easy_axis_direction": "..." or null,
  "exchange_coupling_J_meV": number or null,
  "heisenberg_J_meV": number or null,
  "formation_energy_eV": number or null,
  "band_gap_eV": number or null,
  "band_gap_direct_eV": number or null,
  "band_gap_indirect_eV": number or null,
  "VBM_eV": number or null,
  "CBM_eV": number or null,
  "fermi_energy_eV": number or null,
  "total_energy_eV": number or null,
  "dos_at_fermi": number or null,
  "dos_total_at_fermi": number or null,
  "dos_co_d_at_fermi": number or null,
  "co_d_center_of_mass_eV": number or null,
  "co_d_width_eV": number or null,
  "co_d_occupation": number or null,
  "co_d_spin_up_occupation": number or null,
  "co_d_spin_down_occupation": number or null,
  "anderson_epsilon_d_eV": number or null,
  "anderson_U_eV": number or null,
  "anderson_Gamma_eV": number or null,
  "anderson_V_eV": number or null,
  "anderson_D_eV": number or null,
  "nrg_impurity_entropy_kB": number or null,
  "nrg_specific_heat_coefficient": number or null,
  "nrg_magnetic_susceptibility": number or null,
  "nrg_wilson_ratio": number or null,
  "nrg_kondo_peak_width_meV": number or null,
  "nrg_spectral_weight_at_fermi": number or null,
  "nrg_lambda": number or null,
  "nrg_kept_states": integer or null,
  "functional": "..." or null,
  "dft_code": "..." or null,
  "dft_functional_family": "..." or null,
  "hubbard_U_Zn_eV": number or null,
  "hubbard_U_O_eV": number or null,
  "hubbard_U_co_eV": number or null,
  "hubbard_J_co_eV": number or null,
  "charge_state": "..." or null,
  "ecutwfc_Ry": number or null,
  "k_points_grid": "..." or null,
  "pseudopotential_type": "..." or null,
  "paper_year": integer or null,
  "paper_authors": "..." or null,
  "paper_journal": "..." or null,
  "experimental_vs_theoretical": "..." or null
}}

PAPER TEXT:
{text}

PDF METADATA:
- Number of pages: {pdf_data['num_pages']}
- Title: {pdf_data['metadata'].get('/Title', 'N/A')}
- Author: {pdf_data['metadata'].get('/Author', 'N/A')}
"""

        # Send to Claude
        print("Analyzing Kondo physics data with the Claude API...")
        # Created before the API call so it exists on every path below.
        result = {
            "pdf_file": pdf_file,
            "num_pages": pdf_data['num_pages'],
            "metadata": pdf_data['metadata'],
            "status": "ok",
        }
        try:
            response = self.client.messages.create(
                model=self.model_name,
                max_tokens=4096,
                messages=[
                    {
                        "role": "user",
                        "content": kondo_prompt
                    }
                ]
            )
        except Exception as e:
            # Nothing to parse after an API failure. Stop explicitly (before any
            # Excel file is written) so the caller records a real error instead
            # of a masked UnboundLocalError or an empty "successful" row.
            raise RuntimeError(f"Claude API call failed for {pdf_file}: {e!r}") from e

        # Get the text from the response
        response_text = response.content[0].text.strip()
        result["raw_response"] = response_text

        try:
            # Strip Markdown code fences
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0]
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0]

            extracted_json = json.loads(response_text.strip())
            result["extracted_json"] = extracted_json

            # Map onto the schema; fill missing fields
            kondo_data = KONDO_SCHEMA.copy()
            for key in kondo_data.keys():
                if key in extracted_json:
                    value = extracted_json[key]
                    # Convert "null"-like strings to Python None
                    if value == "null" or value == "None" or value == "N/A":
                        kondo_data[key] = None
                    else:
                        kondo_data[key] = value

            # Convert to a one-row DataFrame
            df = pd.DataFrame([kondo_data])

            print(f"✓ Extracted {len(df.columns)} fields using the Kondo schema")

        except Exception as e:
            print(f"JSON parse error: {e}")
            print("Falling back to an empty schema row; raw response is kept.")
            result["status"] = "parse_error"
            result["error"] = repr(e)

            # Use an empty schema row on parse failure
            kondo_data = KONDO_SCHEMA.copy()
            kondo_data["title"] = pdf_data['metadata'].get('/Title', 'Unknown')
            df = pd.DataFrame([kondo_data])

        # Excel'e kaydet
        print(f"Saving results to Excel: {output_excel}")

        with pd.ExcelWriter(output_excel, engine='openpyxl') as writer:
            # Main data - Kondo schema
            df.to_excel(writer, sheet_name='Kondo_Data', index=False)

            # PDF information
            pdf_info_df = pd.DataFrame([{
                'PDF File': pdf_file,
                'Pages': pdf_data['num_pages'],
                'Title': pdf_data['metadata'].get('/Title', 'N/A'),
                'Author': pdf_data['metadata'].get('/Author', 'N/A'),
                'Subject': pdf_data['metadata'].get('/Subject', 'N/A'),
                'Creator': pdf_data['metadata'].get('/Creator', 'N/A'),
            }])
            pdf_info_df.to_excel(writer, sheet_name='PDF_Info', index=False)

            # Raw Claude response
            if "raw_response" in result:
                response_df = pd.DataFrame([{
                    'Raw Response': result['raw_response']
                }])
                response_df.to_excel(writer, sheet_name='Claude_Response', index=False)

        print(f"✓ Kondo data extraction finished. Saved to '{output_excel}'.")

        result["dataframe"] = df
        result["output_file"] = output_excel

        return result

    def batch_extract_kondo_data(
        self,
        pdf_files: List[str],
        output_excel: str = "kondo_results_claude.xlsx",
        max_chars: int = 200000
    ) -> pd.DataFrame:
        """
        Extract Kondo data from several PDFs in batch and merge the results
        into a single Excel file.

        Args:
            pdf_files: List of PDF files to process
            output_excel: Merged output Excel file
            max_chars: Maximum characters sent to Claude (default: 200000)

        Returns:
            pd.DataFrame: Merged data extracted from all PDFs
        """
        all_records = []
        total = len(pdf_files)

        print("=" * 70)
        print(f"Batch Kondo Data Extraction (Claude API) - {total} PDFs")
        print("=" * 70)
        print()

        for i, pdf_file in enumerate(pdf_files, 1):
            print(f"[{i}/{total}] Processing: {Path(pdf_file).name}")
            print("-" * 70)

            try:
                # Create a temporary Excel file
                temp_excel = f"temp_{Path(pdf_file).stem}.xlsx"

                result = self.extract_kondo_data_from_pdf(
                    pdf_file=pdf_file,
                    output_excel=temp_excel,
                    max_chars=max_chars
                )

                # Add the row to the list
                record = result['dataframe'].to_dict('records')[0]
                record['pdf_file'] = Path(pdf_file).name
                record['extraction_status'] = result.get('status', 'ok')
                all_records.append(record)

                print(f"  Status: {record['extraction_status']}")

                # Delete the temporary file
                Path(temp_excel).unlink(missing_ok=True)

            except Exception as e:
                print(f"  ✗ Error: {e}")
                # Add an empty schema row that records the failure
                error_record = KONDO_SCHEMA.copy()
                error_record["title"] = f"ERROR: {Path(pdf_file).name}"
                error_record["pdf_file"] = Path(pdf_file).name
                error_record["extraction_status"] = "error"
                error_record["error"] = repr(e)
                all_records.append(error_record)

            print()

        # Merge all records
        final_df = pd.DataFrame(all_records)

        # Excel'e kaydet
        print("=" * 70)
        print(f"Saving merged results: {output_excel}")

        with pd.ExcelWriter(output_excel, engine='openpyxl') as writer:
            final_df.to_excel(writer, sheet_name='Kondo_Data', index=False)

        # Only rows with a parsed model response count as successful
        successful = sum(1 for r in all_records if r.get('extraction_status') == 'ok')

        print(f"✓ Done: {successful}/{total} successful")
        print(f"✓ Results: {output_excel}")
        print("=" * 70)

        return final_df
