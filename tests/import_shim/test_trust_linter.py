import tree_sitter_python as tspython
from tree_sitter import Language

from beaker_kernel.lib.code_analysis.analyzer import AnalysisEngine
# from beaker_kernel.lib.code_analysis.rules.trust.categories import trust_assumptions_category, trust_grounding_category
from beaker_kernel.lib.code_analysis.rules.trust.rules import all_rules, ast_rules, llm_rules
from beaker_kernel.lib.code_analysis.analysis_types import AnalysisCodeCell, AnalysisCodeCells


hercules_nb: AnalysisCodeCells = AnalysisCodeCells([
    AnalysisCodeCell(
        cell_id="nb1-c1",
        notebook_id="nb1",
        content="""\
# Let's search for the empty weight of a C-130 Hercules from a reliable source.
import requests
from bs4 import BeautifulSoup

# URL of a reliable source for aircraft specifications
url = "https://www.lockheedmartin.com/en-us/products/c130.html"

# Send a request to the website
response = requests.get(url)

# Parse the HTML content
soup = BeautifulSoup(response.content, 'html.parser')

# Extract the relevant information
# This is a placeholder for the actual extraction logic, as the structure of the page may vary
# For demonstration, let's assume we find the weight in a specific tag or class
empty_weight_info = soup.find_all(text=lambda text: "empty weight" in text.lower())

empty_weight_info
"""
    ),
    AnalysisCodeCell(
        cell_id="nb1-c2",
        notebook_id="nb1",
        content="""\
# Constants
empty_weight_kg = 34400  # Empty weight of C-130 Hercules in kg
empty_weight_lbs = empty_weight_kg * 2.20462  # Convert kg to lbs

# Assuming the aircraft lands on all four wheels, we need to estimate the contact area.
# Let's assume each wheel has a contact area of 1 square foot (a rough estimate).
contact_area_per_wheel_sqft = 1  # square feet

total_contact_area_sqft = 4 * contact_area_per_wheel_sqft  # Total contact area for 4 wheels

# Calculate pressure exerted by the aircraft on the ice
pressure_psi = empty_weight_lbs / total_contact_area_sqft
pressure_psi
"""
    ),
    AnalysisCodeCell(
        cell_id="nb1-c3",
        notebook_id="nb1",
        content="""\
# Bearing strength of sea ice in psi
bearing_strength_psi = 500  # A typical safe estimate for sea ice

# Calculate the required ice thickness
# The thickness is proportional to the pressure exerted divided by the bearing strength
required_ice_thickness = pressure_psi / bearing_strength_psi
required_ice_thickness
"""
    ),
])


async def test_list_literals():
    code = """
# Mutations we are looking for:
oncogene_mutations = ["EGFR", "KRAS", "TP53", "STK11"]
other_mutations = [class(foo), oncogene_mutations,]
mixed_mutations = [class(foo), "KRAS", 11, None, 4.13]
tuple_mutations = ("STK11", 8.2, 5, None)

tb_mutation = "FDRR"

evaluate(oncogene_mutations)
"""
    cell = AnalysisCodeCell(
        cell_id=test_list_literals.__name__,
        notebook_id='test',
        content=code
    )
    from beaker_kernel.lib.code_analysis import AnalysisASTRule
    from beaker_kernel.lib.code_analysis.rules.trust.categories import literal_value_issue
    from beaker_kernel.lib.code_analysis.rules.trust.rules import trust_literal_check_filter

    rule = AnalysisASTRule(
        id="trust_literal_check",
        issue=literal_value_issue,
        filter=trust_literal_check_filter,
    )

    language = Language(tspython.language())
    analyzer = AnalysisEngine(rules=[rule], language=language)

    results = await analyzer.analyze(AnalysisCodeCells([cell]))

    assert len(results) == 11
    expected_values = [
        '"EGFR"',
        '"KRAS"',
        '"TP53"',
        '"STK11"',

        '"KRAS"',
        '11',
        '4.13',

        '"STK11"',
        '8.2',
        '5',

        '"FDRR"',
    ]
    # Extract code portions from results to compare against expected values
    assert [code[r.start:r.end] for r in results] == expected_values


async def test_multi_codecell_ast():
    language = Language(tspython.language())
    analyzer = AnalysisEngine(rules=ast_rules, language=language)
    nb = hercules_nb
    cell_map = {cell.cell_id: cell for cell in nb}
    results = await analyzer.analyze(nb)

    assert len(results) == 4
    expected_values = [
        '"https://www.lockheedmartin.com/en-us/products/c130.html"',
        '34400',
        '1',
        '500',
    ]
    # Extract code portions from results to compare against expected values
    found_values = [
        cell_map[r.cell_id].content[r.start:r.end] for r in results
    ]
    assert found_values == expected_values
