import asyncio
import sys
from evals.evaluator import PromptEvaluator


async def main():
    print("=" * 75)
    print("INICIANDO PROMPT EVALS & LLM QUALITY GATES PRÉ-DEPLOY")
    print("=" * 75)

    evaluator = PromptEvaluator(min_required_score=0.90)
    report = await evaluator.run_evals()

    print(f"\nTotal de Cenários Avaliados: {report.total_scenarios}")
    print(f"Cenários Aprovados:         {report.passed_scenarios} / {report.total_scenarios}")
    print(f"Score Global de Qualidade:   {report.global_score * 100:.2f}% (Mínimo: {report.min_required_score * 100:.2f}%)")
    print("-" * 75)

    for res in report.results:
        status_tag = "[APROVADO]" if res.passed else "[FALHA]"
        print(f"\n{status_tag} {res.scenario_name} (ID: {res.scenario_id})")
        print(f"  • Entrada do Usuário: \"{res.user_input}\"")
        print(f"  • Score: {res.score * 100:.1f}% | Segurança: {res.safety_score * 100:.0f}% | Fidelidade: {res.fidelity_score * 100:.0f}% | Relevância: {res.relevance_score * 100:.0f}%")
        print(f"  • Transbordo Humano: {res.human_handoff}")
        print(f"  • Resposta do Bot: {res.bot_response[:120]}..." if len(res.bot_response) > 120 else f"  • Resposta do Bot: {res.bot_response}")

        if res.violations:
            print("  • Observações / Violações:")
            for v in res.violations:
                print(f"    - {v}")

    print("\n" + "=" * 75)
    if report.quality_gate_passed:
        print("RESULTADO DO QUALITY GATE: APROVADO PARA DEPLOY EM PRODUÇÃO")
        print("=" * 75)
        sys.exit(0)
    else:
        print("RESULTADO DO QUALITY GATE: REPROVADO - DEPLOY BLOQUEADO")
        print(f"Motivo: Score abaixo do limiar mínimo ({report.min_required_score * 100}%) ou violação de política de segurança.")
        print("=" * 75)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
