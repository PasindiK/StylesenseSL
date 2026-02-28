"""
Ad-hoc CLI for the CatalogAgent.

Examples:
  python scripts/agent_cli.py --search "vintage" --limit 5
  python scripts/agent_cli.py --tag "Monochrome" --recommend 5
  python scripts/agent_cli.py --id 3
  python scripts/agent_cli.py --category "BEACH WEAR" --color Navy --max_price 5000
  python scripts/agent_cli.py --interactive
"""
import argparse
import json
import sys

from src.agents.catalog_agent import CatalogAgent


def print_json(obj):
    print(json.dumps(obj, indent=2, ensure_ascii=False))


def main(argv=None):
    parser = argparse.ArgumentParser(description='CatalogAgent CLI')
    parser.add_argument('--search', '-s', help='Text search query')
    parser.add_argument('--tag', '-t', help='Style tag to filter or recommend')
    parser.add_argument('--recommend', '-r', type=int, nargs='?', const=5,
                        help='If provided with --tag, recommend top N similar by tag (default 5)')
    parser.add_argument('--id', '-i', help='Product id to fetch')
    parser.add_argument('--category', '-c', help='Category filter')
    parser.add_argument('--color', help='Color filter')
    parser.add_argument('--max_price', type=float, help='Max price filter (numeric)')
    parser.add_argument('--limit', '-l', type=int, default=20, help='Limit results')
    parser.add_argument('--interactive', action='store_true', help='Start interactive prompt')

    args = parser.parse_args(argv)

    agent = CatalogAgent()

    if args.interactive:
        try:
            while True:
                q = input('\nEnter command (search/tag/id/filters/quit): ').strip()
                if not q:
                    continue
                if q.lower() in ('q', 'quit', 'exit'):
                    break
                parts = q.split()
                cmd = parts[0].lower()
                if cmd == 'search':
                    query = ' '.join(parts[1:])
                    res = agent.search_by_text(query, limit=args.limit)
                    print_json(res)
                elif cmd == 'tag':
                    tag = ' '.join(parts[1:])
                    res = agent.find_by_filters(tag=tag)
                    print_json(res)
                elif cmd == 'recommend':
                    tag = ' '.join(parts[1:])
                    res = agent.recommend_similar_by_tag(tag, top_n=args.limit)
                    print_json(res)
                elif cmd == 'id':
                    pid = parts[1]
                    res = agent.get_product_by_id(pid)
                    print_json(res)
                elif cmd == 'filters':
                    # simple parser: filters category=... color=... max_price=...
                    kw = {}
                    for token in parts[1:]:
                        if '=' in token:
                            k, v = token.split('=', 1)
                            if k == 'max_price':
                                try:
                                    v = float(v)
                                except Exception:
                                    print('invalid max_price')
                                    continue
                            kw[k] = v
                    res = agent.find_by_filters(category=kw.get('category'), color=kw.get('color'),
                                                 max_price=kw.get('max_price'), tag=kw.get('tag'))
                    print_json(res)
                else:
                    print('unknown command')
        except (KeyboardInterrupt, EOFError):
            print('\nexiting')
        return 0

    # non-interactive mode
    if args.id:
        res = agent.get_product_by_id(str(args.id))
        print_json(res)
        return 0

    if args.search:
        res = agent.search_by_text(args.search, limit=args.limit)
        print_json(res)
        return 0

    # tag + recommend
    if args.tag and args.recommend:
        res = agent.recommend_similar_by_tag(args.tag, top_n=args.recommend)
        print_json(res)
        return 0

    # filters
    if args.category or args.color or args.tag or args.max_price:
        res = agent.find_by_filters(category=args.category, color=args.color,
                                    max_price=args.max_price, tag=args.tag)
        # enforce limit
        if isinstance(res, list):
            print_json(res[:args.limit])
        else:
            print_json(res)
        return 0

    parser.print_help()
    return 1


if __name__ == '__main__':
    sys.exit(main())
