"""Test CIMA filtering, pagination, package grouping, and national code lookup."""

import asyncio

import httpx
import pytest

from medclue_api.cima_client import CimaClient
from medclue_api.matching import find_presentation_matches
from medclue_api.schemas import MedicationCandidate, VerifyRequest


def medication(registration="000001", name="EXAMPLE 500 mg COMPRIMIDOS EFG", strength="500 mg", form="COMPRIMIDO", codes=("000010", "000020")):
    return {
        "nregistro": registration,
        "nombre": name,
        "dosis": strength,
        "formaFarmaceutica": {"nombre": form},
        "presentaciones": [
            {"cn": code, "nombre": f"{name}, {index + 1}0 comprimidos"}
            for index, code in enumerate(codes)
        ],
    }


def search_page(medications, page=1, total=None, page_size=200):
    return {
        "pagina": page,
        "totalFilas": len(medications) if total is None else total,
        "tamanioPagina": page_size,
        "resultados": [
            {key: value for key, value in item.items() if key != "presentaciones"}
            for item in medications
        ],
    }


@pytest.fixture
def cima_client(monkeypatch):
    requests = []
    responses = []

    def handle_request(request):
        requests.append(request)
        response = responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    real_client = httpx.AsyncClient

    def create_client(**kwargs):
        return real_client(**kwargs, transport=httpx.MockTransport(handle_request), trust_env=False)

    monkeypatch.setattr("medclue_api.cima_client.httpx.AsyncClient", create_client)
    client = CimaClient()
    yield client, requests, responses
    asyncio.run(client.close())


def test_search_only_requests_details_for_matching_names(cima_client):
    client, requests, responses = cima_client
    selected = medication()
    others = [medication("000002", name="ANOTHER 500 mg COMPRIMIDOS"),
              medication("000003", name="EXAMPLE FORTE 500 mg COMPRIMIDOS")]
    responses.extend([httpx.Response(200, json=search_page([*others, selected])),
                      httpx.Response(200, json=selected)])

    results = asyncio.run(client.search_presentations("  EXAMPLE  "))

    assert len(results) == 1
    assert requests[0].url.params["nombre"] == "example"
    assert [dict(request.url.params) for request in requests[1:]] == [{"nregistro": "000001"}]
    assert responses == []


@pytest.mark.parametrize("query", ["Example+Plus", "  Éxample - Plus  "])
def test_search_keeps_small_name_differences(cima_client, query):
    client, requests, responses = cima_client
    selected = medication(name="EXAMPLE PLUS 500 mg COMPRIMIDOS EFG")
    responses.extend([httpx.Response(200, json=search_page([selected])), httpx.Response(200, json=selected)])

    results = asyncio.run(client.search_presentations(query))

    assert len(results) == 1
    assert len(requests) == 2


@pytest.mark.parametrize("strength", [None, "5%", "875 mg + 125 mg"])
def test_search_keeps_names_when_strength_is_missing_or_complex(cima_client, strength):
    client, requests, responses = cima_client
    selected = medication(name="EXAMPLE 5% CREMA", strength=strength, form="CREMA")
    responses.extend([httpx.Response(200, json=search_page([selected])), httpx.Response(200, json=selected)])

    results = asyncio.run(client.search_presentations("Example"))

    assert len(results) == 1
    assert len(requests) == 2


def test_filtered_first_page_does_not_hide_matches_on_later_pages(cima_client):
    client, requests, responses = cima_client
    other = medication("000002", name="ANOTHER 500 mg COMPRIMIDOS")
    selected = medication()
    responses.extend([
        httpx.Response(200, json=search_page([other], total=2, page_size=1)),
        httpx.Response(200, json=search_page([selected], page=2, total=2, page_size=1)),
        httpx.Response(200, json=selected),
    ])

    results = asyncio.run(client.search_presentations("Example"))

    assert len(results) == 1
    assert [request.url.params["pagina"] for request in requests[:2]] == ["1", "2"]
    assert dict(requests[2].url.params) == {"nregistro": "000001"}


def test_candidates_on_different_pages_remain_distinct(cima_client):
    client, requests, responses = cima_client
    first = medication(codes=("000010",))
    second = medication("000002", codes=("000020",))
    responses.extend([
        httpx.Response(200, json=search_page([first], total=2, page_size=1)),
        httpx.Response(200, json=search_page([second], page=2, total=2, page_size=1)),
        httpx.Response(200, json=first), httpx.Response(200, json=second),
    ])

    results = asyncio.run(client.search_presentations("Example"))
    candidate = MedicationCandidate(name="Example", strength="500 mg", form="tablet")

    assert len(results) == 2
    assert len(requests) == 4
    assert find_presentation_matches(candidate, results).verified is None


def test_repeated_search_records_do_not_duplicate_options(cima_client):
    client, requests, responses = cima_client
    selected = medication()
    responses.extend([httpx.Response(200, json=search_page([selected, selected])),
                      httpx.Response(200, json=selected), httpx.Response(200, json=selected)])

    assert len(asyncio.run(client.search_presentations("Example"))) == 1
    assert len(requests) == 3


def test_only_unrelated_results_do_not_trigger_detail_requests(cima_client):
    client, requests, responses = cima_client
    responses.append(httpx.Response(200, json=search_page([medication(name="ANOTHER 500 mg COMPRIMIDOS")])))

    assert asyncio.run(client.search_presentations("Example")) == []
    assert len(requests) == 1


def test_package_sizes_become_one_option_with_a_usable_code(cima_client):
    client, requests, responses = cima_client
    selected = medication()
    responses.extend([httpx.Response(200, json=search_page([selected])),
                      httpx.Response(200, json=selected), httpx.Response(200, json=selected)])

    results = asyncio.run(client.search_presentations("Example"))
    request = VerifyRequest(national_code=results[0].national_code)
    verified = asyncio.run(client.get_presentation(request.national_code))
    candidate = MedicationCandidate(name="Example", strength="500 mg", form="tablet")

    assert len(results) == 1
    assert verified == results[0]
    assert results[0].national_code == "000010"
    assert find_presentation_matches(candidate, results).verified == verified
    assert requests[-1].url.params["cn"] == "000010"


@pytest.mark.parametrize("code", ["000010", "000020"])
def test_any_package_code_can_still_be_verified(cima_client, code):
    client, requests, responses = cima_client
    responses.append(httpx.Response(200, json=medication()))

    result = asyncio.run(client.get_presentation(code))

    assert result.national_code == code
    assert result.registration_number == "000001"
    assert dict(requests[0].url.params) == {"cn": code}


@pytest.mark.parametrize(
    "changes",
    [
        {"registration": "000002"},
        {"name": "EXAMPLE 250 mg COMPRIMIDOS", "strength": "250 mg"},
        {"name": "EXAMPLE 500 mg CAPSULAS", "form": "CAPSULA"},
    ],
)
def test_search_keeps_different_doses_forms_and_registrations(cima_client, changes):
    client, _, responses = cima_client
    first = medication(codes=("000010",))
    second = medication(codes=("000020",), **changes)
    responses.extend([
        httpx.Response(200, json=search_page([first, second])),
        httpx.Response(200, json=first), httpx.Response(200, json=second),
    ])

    results = asyncio.run(client.search_presentations("Example"))

    assert [result.national_code for result in results] == ["000010", "000020"]
    assert results[0] != results[1]


@pytest.mark.parametrize("changes", [{"pagina": 2}, {"totalFilas": -1}, {"tamanioPagina": 0}, {"resultados": None}, {"totalFilas": 2}])
def test_invalid_or_incomplete_pages_are_not_treated_as_unique_results(cima_client, changes):
    client, requests, responses = cima_client
    responses.append(httpx.Response(200, json={**search_page([medication()]), **changes}))

    with pytest.raises(ValueError):
        asyncio.run(client.search_presentations("Example"))
    assert len(requests) == 1


def test_missing_later_page_remains_an_error(cima_client):
    client, _, responses = cima_client
    responses.extend([httpx.Response(200, json=search_page([medication()], total=2, page_size=1)),
                      httpx.Response(204)])

    with pytest.raises(ValueError):
        asyncio.run(client.search_presentations("Example"))


@pytest.mark.parametrize("code", [429, 500, 503])
def test_http_failures_are_not_no_match_results(cima_client, code):
    client, requests, responses = cima_client
    responses.append(httpx.Response(code))

    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(client.search_presentations("Example"))
    assert len(requests) == 1


@pytest.mark.parametrize("error", [httpx.ConnectError("Simulated failure"), httpx.ReadTimeout("Simulated timeout")])
def test_network_failures_are_not_no_match_results(cima_client, error):
    client, requests, responses = cima_client
    responses.append(error)

    with pytest.raises(type(error)):
        asyncio.run(client.search_presentations("Example"))
    assert len(requests) == 1


def test_general_form_suffix_variation_survives_search_grouping_and_matching(cima_client):
    client, requests, responses = cima_client
    selected = medication(
        name="ASPIRINA C 400 mg/240 mg COMPRIMIDOS EFERVESCENTES",
        strength="400/240 mg/mg", form="COMPRIMIDO EFERVESCENTE",
    )
    responses.extend([httpx.Response(200, json=search_page([selected])),
                      httpx.Response(200, json=selected)])

    presentations = asyncio.run(client.search_presentations("Aspirina C"))
    candidate = MedicationCandidate(name="Aspirina C", strength="400 mg + 240 mg", form="COMPRIMIDO EFERVESCENTE")
    result = find_presentation_matches(candidate, presentations)

    assert len(requests) == 2
    assert len(result.presentations) == 1
    assert result.verified == presentations[0]
