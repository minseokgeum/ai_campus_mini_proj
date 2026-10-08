"""생성된 결과 파일 일괄 정리. 기본은 목록 확인, --apply일 때만 삭제."""
import argparse
from .output import owned_files


def clean_results(project_root=None, apply=False):
    """[팀 폴더 반영] 생성 목록의 파일만 삭제하며 팀의 폴더 구조와 다른 자료는 보존한다."""
    files = [path for path in owned_files(project_root) if path.exists()]
    if apply:
        for path in files:
            path.unlink()
    return files


def main():
    parser = argparse.ArgumentParser(description="이 모델이 생성한 결과물만 정리")
    parser.add_argument("--project-root", help="팀 저장소 최상위 폴더. 생략하면 코드 위치로 결정")
    parser.add_argument("--apply", action="store_true", help="목록을 실제 삭제")
    args = parser.parse_args()
    files = clean_results(args.project_root, args.apply)
    for path in files:
        print(path)
    print(f"{'삭제 완료' if args.apply else '삭제 예정(실제 삭제는 --apply)'}: {len(files)}개")


if __name__ == "__main__":
    main()
